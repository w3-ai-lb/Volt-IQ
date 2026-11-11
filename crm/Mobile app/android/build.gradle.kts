// ==========================================
// PART 1: Buildscript / Plugin definitions
// ==========================================
buildscript {
    repositories {
        google()
        mavenCentral()
    }
    dependencies {
        classpath("com.android.tools.build:gradle:8.11.1")
        classpath("org.jetbrains.kotlin:kotlin-gradle-plugin:2.2.20")
    }
}

// ==========================================
// PART 2: Repository configuration
// ==========================================
allprojects {
    repositories {
        google()
        mavenCentral()
    }
}

// ==========================================
// PART 3: Build directory configuration
// ==========================================
val newBuildDir: Directory =
    rootProject.layout.buildDirectory
        .dir("../../build")
        .get()
rootProject.layout.buildDirectory.value(newBuildDir)

subprojects {
    val newSubprojectBuildDir: Directory = newBuildDir.dir(project.name)
    project.layout.buildDirectory.value(newSubprojectBuildDir)
}
subprojects {
    project.evaluationDependsOn(":app")
}

// ==========================================
// PART 4: Clean task
// ==========================================
tasks.register<Delete>("clean") {
    delete(rootProject.layout.buildDirectory)
}
