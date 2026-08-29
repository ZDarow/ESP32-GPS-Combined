# ESP32GPSTracker ProGuard Rules

# =============================================
# Android & Kotlin
# =============================================
-keepattributes *Annotation*
-keepattributes SourceFile,LineNumberTable
-keepattributes Signature
-keepattributes InnerClasses,EnclosingMethod

# Kotlin
-keep class kotlin.** { *; }
-keep class kotlin.Metadata { *; }
-dontwarn kotlin.**
-keepclassmembers class kotlin.Metadata {
    public <methods>;
}

# Coroutines
-keepnames class kotlinx.coroutines.internal.MainDispatcherFactory {}
-keepnames class kotlinx.coroutines.CoroutineExceptionHandler {}
-keepclassmembers class kotlinx.** {
    volatile <fields>;
}

# =============================================
# Jetpack Compose
# =============================================
-keep class androidx.compose.** { *; }
-dontwarn androidx.compose.**

# Compose Runtime
-keep class androidx.compose.runtime.** { *; }
-keepclassmembers class androidx.compose.runtime.** {
    volatile <fields>;
}

# Compose UI
-keep class androidx.compose.ui.** { *; }
-keepclassmembers class androidx.compose.ui.** {
    volatile <fields>;
}

# Compose Foundation
-keep class androidx.compose.foundation.** { *; }
-keepclassmembers class androidx.compose.foundation.** {
    volatile <fields>;
}

# Compose Material3
-keep class androidx.compose.material3.** { *; }
-keepclassmembers class androidx.compose.material3.** {
    volatile <fields>;
}

# =============================================
# Nordic BLE Library
# =============================================
-keep class no.nordicsemi.android.ble.** { *; }
-keepclassmembers class * extends no.nordicsemi.android.ble.BleManager {
    <init>(...);
    <fields>;
    <methods>;
}
-dontwarn no.nordicsemi.android.ble.**

# =============================================
# OSMDroid
# =============================================
-dontwarn org.osmdroid.**
-keep class org.osmdroid.** { *; }

# =============================================
# AndroidX
# =============================================
-keep class androidx.** { *; }
-dontwarn androidx.**

# Lifecycle
-keep class androidx.lifecycle.** { *; }
-keepclassmembers class androidx.lifecycle.** {
    volatile <fields>;
}

# Core
-keep class androidx.core.** { *; }
-keepclassmembers class androidx.core.** {
    volatile <fields>;
}

# =============================================
# Data Classes (GPS fix, NMEA)
# =============================================
-keep class com.example.esp32gps.** { *; }
-keepclassmembers class com.example.esp32gps.** {
    <fields>;
    <init>(...);
}

# =============================================
# Data classes serialization
# =============================================
-keepclassmembers class * {
    @com.google.gson.annotations.SerializedName <fields>;
}

# =============================================
# OSMDroid requires reflection for tile sources
# =============================================
-keepclassmembers class org.osmdroid.tileprovider.** {
    <fields>;
    <methods>;
}
-keepclassmembers class org.osmdroid.config.** {
    <fields>;
    <methods>;
}
