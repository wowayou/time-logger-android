import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

// 版本锚点由 scripts/sync_runtime.py 写入（单一真源＝web 仓的 manifest version）。
// 缺文件时用占位值，让「没同步过运行时」在构建期就看得出来，而不是装到手机上才发现。
val runtimeProps = Properties().apply {
    val f = rootProject.file("app/version.properties")
    if (f.exists()) f.inputStream().use { load(it) }
}
val webVersion = (runtimeProps.getProperty("web.version") ?: "0").toInt()
val androidRevision = (runtimeProps.getProperty("android.revision") ?: "0").toInt()

android {
    namespace = "org.eigentime.timelogger"
    compileSdk = 36

    defaultConfig {
        applicationId = "org.eigentime.timelogger"
        minSdk = 26
        targetSdk = 36
        versionCode = webVersion * 100 + androidRevision
        versionName = "$webVersion.$androidRevision"
    }

    androidResources {
        // 只打包 zh / en 两套文案（web 运行时同样只有这两种），别的语言不留空壳。
        localeFilters += listOf("zh", "en")
    }

    signingConfigs {
        // 自用侧载：debug 签名即可。上架时在 keystore.properties 里给出真实密钥，
        // 文件本身不进版本库（.gitignore 已挡）。
        create("release") {
            val ksProps = Properties()
            val f = rootProject.file("keystore.properties")
            if (f.exists()) {
                f.inputStream().use { ksProps.load(it) }
                storeFile = rootProject.file(ksProps.getProperty("storeFile"))
                storePassword = ksProps.getProperty("storePassword")
                keyAlias = ksProps.getProperty("keyAlias")
                keyPassword = ksProps.getProperty("keyPassword")
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            isShrinkResources = false
            val ksConfigured = rootProject.file("keystore.properties").exists()
            signingConfig = if (ksConfigured) signingConfigs.getByName("release")
            else signingConfigs.getByName("debug")
        }
        debug {
            applicationIdSuffix = ".debug"
            versionNameSuffix = "-debug"
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlin {
        compilerOptions {
            jvmTarget = org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17
        }
    }
    sourceSets {
        getByName("main") {
            kotlin.srcDirs("src/main/kotlin")
        }
    }
    packaging {
        resources.excludes += setOf("META-INF/*.kotlin_module")
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.17.0")
    implementation("androidx.webkit:webkit:1.17.0")
    testImplementation("junit:junit:4.13.2")
}

// 构建前强制检查内嵌运行时在位：assets/app 不进版本库，忘了同步就该在这里失败，
// 而不是产出一个白屏 APK。
val assertRuntimeSynced by tasks.registering {
    doFirst {
        val index = file("src/main/assets/app/index.html")
        if (!index.exists()) {
            throw GradleException(
                "内嵌运行时缺失：请先运行 python3 scripts/sync_runtime.py（从 web 仓同步 sw.js FILES 清单）"
            )
        }
        if (webVersion == 0) {
            throw GradleException("app/version.properties 缺失或未写入 web.version：请先运行 sync_runtime.py")
        }
    }
}
tasks.matching { it.name.startsWith("merge") && it.name.endsWith("Assets") }.configureEach {
    dependsOn(assertRuntimeSynced)
}
