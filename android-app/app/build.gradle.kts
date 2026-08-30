plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jlleitschuh.gradle.ktlint")
    id("io.gitlab.arturbosch.detekt")
}

android {
    namespace = "com.example.esp32gps"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.example.esp32gps"
        minSdk = 26
        targetSdk = 35
        versionCode = 1
        versionName = "1.0"
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro",
            )
        }
        debug {
            isMinifyEnabled = false
        }
    }

    buildFeatures {
        compose = true
    }
    composeOptions {
        kotlinCompilerExtensionVersion = "1.5.14"
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
    packaging {
        resources {
            excludes += "/META-INF/{AL2.0,LGPL2.1}"
        }
    }
}

configurations.all {
    resolutionStrategy {
        force("org.jetbrains.kotlin:kotlin-stdlib:1.9.24")
        force("org.jetbrains.kotlin:kotlin-stdlib-jdk8:1.9.24")
        force("org.jetbrains.kotlin:kotlin-stdlib-jdk7:1.9.24")
        force("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.8.1")
        force("org.jetbrains.kotlinx:kotlinx-coroutines-core:1.8.1")
        force("androidx.lifecycle:lifecycle-viewmodel-compose:2.7.0")
        force("androidx.lifecycle:lifecycle-runtime-compose:2.7.0")
        force("androidx.compose.ui:ui-android:1.6.0")
        force("androidx.compose.ui:ui-tooling-android:1.6.0")
        force("androidx.compose.ui:ui-tooling-preview-android:1.6.0")
        force("androidx.compose.ui:ui-graphics-android:1.6.0")
        force("androidx.compose.ui:ui-text-android:1.6.0")
        force("androidx.compose.foundation:foundation-android:1.6.0")
        force("androidx.compose.foundation:foundation-layout-android:1.6.0")
        force("androidx.compose.animation:animation-android:1.6.0")
        force("androidx.compose.animation:animation-core-android:1.6.0")
        force("androidx.compose.material3:material3-android:1.2.0")
        force("androidx.compose.runtime:runtime-android:1.6.0")
        force("androidx.compose.runtime:runtime-saveable-android:1.6.0")
        force("androidx.activity:activity-compose:1.8.2")
    }
}

dependencies {
    implementation("no.nordicsemi.android:ble:2.7.5")
    implementation("no.nordicsemi.android:ble-common:2.7.5")

    implementation(platform("androidx.compose:compose-bom:2024.01.00"))
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.activity:activity-compose")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.7.0")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.7.0")

    implementation("org.osmdroid:osmdroid-android:6.1.18")

    implementation("androidx.core:core-ktx:1.12.0")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.8.1")

    debugImplementation("androidx.compose.ui:ui-tooling")
}

detekt {
    buildUponDefaultConfig = true
    allRules = false
    config.setFrom("$rootDir/config/detekt/detekt.yml")
    baseline = file("$rootDir/config/detekt/baseline.xml")
}

ktlint {
    version = "1.3.1"
    filter {
        exclude("**/GpsBleManager.kt")
    }
}
