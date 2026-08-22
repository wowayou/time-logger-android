package org.eigentime.timelogger

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File
import java.nio.file.Files
import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors

class NativeStoreTest {

    private fun store(): Pair<NativeStore, File> {
        val dir = Files.createTempDirectory("tl-store").toFile()
        return NativeStore(dir) to dir
    }

    @Test
    fun `round trips values verbatim`() {
        val (s, _) = store()
        val raw = """{"entries":[{"id":"a1","ts":"2026-08-22T09:00","what":"写代码","tags":["当前主线"]}]}"""
        assertNull(s.setItem("timelog.v1", raw))
        // 逐字一致是 CAS（saveChecked）的前提：raw 变一个字节，跨端写入保护就会误判。
        assertEquals(raw, s.getItem("timelog.v1"))
    }

    @Test
    fun `missing key reads null not empty string`() {
        val (s, _) = store()
        // storage.js 用 getItem 是否为空来区分「全新安装」与「显式清空」，
        // 空串与 null 在那里不是同一件事。
        assertNull(s.getItem("timelog.config"))
        s.setItem("timelog.config", "")
        assertEquals("", s.getItem("timelog.config"))
    }

    @Test
    fun `keys with dots and unicode survive encoding`() {
        val (s, _) = store()
        s.setItem("timelog.widgetMirror.v1", "{}")
        s.setItem("键·带中文", "值")
        assertEquals("{}", s.getItem("timelog.widgetMirror.v1"))
        assertEquals("值", s.getItem("键·带中文"))
        assertTrue(s.keys().containsAll(listOf("timelog.widgetMirror.v1", "键·带中文")))
        assertEquals(2, s.length())
    }

    @Test
    fun `remove and clear drop keys`() {
        val (s, _) = store()
        s.setItem("a", "1")
        s.setItem("b", "2")
        s.removeItem("a")
        assertNull(s.getItem("a"))
        assertEquals(1, s.length())
        s.clear()
        assertEquals(0, s.length())
    }

    @Test
    fun `no tmp files left behind`() {
        val (s, dir) = store()
        s.setItem("timelog.v1", "x")
        s.setItem("timelog.v1", "y")
        val leftovers = dir.listFiles()!!.filter { it.name.endsWith(".tmp") }
        assertTrue("临时文件必须被 rename 消耗掉：$leftovers", leftovers.isEmpty())
    }

    @Test
    fun `concurrent writers never produce a partial read`() {
        val (s, _) = store()
        val long = "L".repeat(200_000)
        val short = "S".repeat(10)
        val pool = Executors.newFixedThreadPool(8)
        val start = CountDownLatch(1)
        val done = CountDownLatch(8)
        val bad = mutableListOf<String>()
        repeat(8) { i ->
            pool.execute {
                start.await()
                repeat(60) {
                    if (i % 2 == 0) s.setItem("timelog.v1", long) else s.setItem("timelog.v1", short)
                    val v = s.getItem("timelog.v1")
                    // 原子写的判据：任何时刻读到的必须是**某一次完整的**写入值，
                    // 不能是两者的拼接或截断。
                    if (v != long && v != short) synchronized(bad) { bad.add("len=${v?.length}") }
                }
                done.countDown()
            }
        }
        start.countDown()
        done.await()
        pool.shutdown()
        assertTrue("读到了半截数据：${bad.take(3)}", bad.isEmpty())
    }
}
