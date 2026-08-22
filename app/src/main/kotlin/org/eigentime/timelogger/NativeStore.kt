package org.eigentime.timelogger

import java.io.File
import java.io.IOException

/**
 * 原生侧的权威存储：web 运行时通过 [StoreBridge] 把 localStorage 的读写落在这里，
 * 小组件 / 磁贴 / 通知也读写同一份数据。
 *
 * 形态刻意选「一个键一个文件」而不是一个大 JSON：
 * - 写入是**每个键各自原子**（tmp + rename + fsync），与 localStorage 的语义对得上；
 * - 改一个小键不必重写整份记录（timelog.v1 真实数据可达数百 KB）；
 * - 不需要在原生侧写 JSON 解析器——这个类因此**不依赖任何 Android API**，
 *   可以用普通 JVM 单测覆盖（契约 §8）。
 *
 * 线程安全：JavascriptInterface 的调用来自 WebView 的 JavaBridge 线程，小组件与
 * 通知的调用来自主线程，所以所有公开方法都在同一把锁内。
 */
class NativeStore(private val dir: File) {

    private val lock = Any()

    init {
        if (!dir.exists()) dir.mkdirs()
    }

    /** 键 → 文件名：只允许 [A-Za-z0-9._-]，其余按 %XX 编码，保证可逆且跨文件系统安全。 */
    private fun fileFor(key: String): File {
        val sb = StringBuilder()
        for (b in key.toByteArray(Charsets.UTF_8)) {
            val c = b.toInt().toChar()
            if (c.isLetterOrDigit() && c.code < 128 || c == '.' || c == '_' || c == '-') sb.append(c)
            else sb.append('%').append(String.format("%02X", b.toInt() and 0xFF))
        }
        return File(dir, sb.toString() + ".val")
    }

    private fun keyOf(file: File): String? {
        val name = file.name
        if (!name.endsWith(".val")) return null
        val encoded = name.removeSuffix(".val")
        val out = java.io.ByteArrayOutputStream()
        var i = 0
        while (i < encoded.length) {
            val c = encoded[i]
            if (c == '%' && i + 2 < encoded.length) {
                val hex = encoded.substring(i + 1, i + 3)
                out.write(hex.toInt(16))
                i += 3
            } else {
                out.write(c.code)
                i += 1
            }
        }
        return String(out.toByteArray(), Charsets.UTF_8)
    }

    fun getItem(key: String): String? = synchronized(lock) {
        val f = fileFor(key)
        if (!f.exists()) return null
        return try {
            f.readText(Charsets.UTF_8)
        } catch (e: IOException) {
            null
        }
    }

    /** @return null 表示写入成功；非 null 是错误名（会在 JS 侧被抛成异常）。 */
    fun setItem(key: String, value: String): String? = synchronized(lock) {
        val target = fileFor(key)
        val tmp = File(dir, target.name + ".tmp")
        return try {
            tmp.outputStream().use { out ->
                out.write(value.toByteArray(Charsets.UTF_8))
                out.flush()
                out.fd.sync()
            }
            if (!tmp.renameTo(target)) {
                tmp.delete()
                "InvalidStateError"
            } else {
                cachedKeys = null
                null
            }
        } catch (e: IOException) {
            tmp.delete()
            // 磁盘满与配额在语义上等价：storage.js 只看「抛没抛」，用户看到的是
            // 「这次改动没有保存」而不是一个技术名词。
            "QuotaExceededError"
        }
    }

    fun removeItem(key: String) = synchronized(lock) {
        fileFor(key).delete()
        cachedKeys = null
        Unit
    }

    fun clear() = synchronized(lock) {
        dir.listFiles()?.forEach { if (it.name.endsWith(".val")) it.delete() }
        cachedKeys = null
        Unit
    }

    private var cachedKeys: List<String>? = null

    fun keys(): List<String> = synchronized(lock) {
        cachedKeys?.let { return it }
        val list = (dir.listFiles() ?: emptyArray())
            .mapNotNull { keyOf(it) }
            .sorted()
        cachedKeys = list
        return list
    }

    fun length(): Int = keys().size

    fun key(index: Int): String? = keys().getOrNull(index)

    /** 供备份/诊断用：整份存储的键与字节数，不含内容。 */
    fun describe(): String = synchronized(lock) {
        keys().joinToString(", ") { k -> "$k=${(getItem(k) ?: "").toByteArray(Charsets.UTF_8).size}B" }
    }
}
