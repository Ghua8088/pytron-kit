#include <jni.h>
#include <string>
#include <android/log.h>
#include <Python.h>
#include <dlfcn.h>
#include <vector>
#include <unistd.h>
#include <fcntl.h> // <--- REQUIRED for open/dup2

#define LOG_TAG "PytronNative"
#define LOGI(...) __android_log_print(ANDROID_LOG_INFO, LOG_TAG, __VA_ARGS__)
#define LOGE(...) __android_log_print(ANDROID_LOG_ERROR, LOG_TAG, __VA_ARGS__)

static JavaVM* gJavaVM = nullptr;
static jobject gMainActivity = nullptr;

// Helper to send message to Java
static PyObject* py_send_to_android(PyObject* self, PyObject* args) {
    const char* message;
    if (!PyArg_ParseTuple(args, "s", &message)) {
        return NULL;
    }

    JNIEnv* env;
    bool needsDetach = false;
    int envStat = gJavaVM->GetEnv((void**)&env, JNI_VERSION_1_6);
    if (envStat == JNI_EDETACHED) {
        gJavaVM->AttachCurrentThread(&env, NULL);
        needsDetach = true;
    }

    if (gMainActivity && env) {
        jclass cls = env->GetObjectClass(gMainActivity);
        jmethodID mid = env->GetMethodID(cls, "onMessageFromPython", "(Ljava/lang/String;)Ljava/lang/String;");
        if (mid) {
            jstring jStr = env->NewStringUTF(message);
            jobject result = env->CallObjectMethod(gMainActivity, mid, jStr);
            env->DeleteLocalRef(jStr);
            if (env->ExceptionCheck()) {
                env->ExceptionDescribe();
                env->ExceptionClear();
            }
        }
    }
    if (needsDetach) gJavaVM->DetachCurrentThread();
    Py_RETURN_NONE;
}

static PyMethodDef AndroidMethods[] = {
    {"send_to_android", py_send_to_android, METH_VARARGS, "Send message to Android layer"},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef androidmodule = {
    PyModuleDef_HEAD_INIT, "_pytron_android", NULL, -1, AndroidMethods
};

PyMODINIT_FUNC PyInit__pytron_android(void) {
    return PyModule_Create(&androidmodule);
}

extern "C" JNIEXPORT void JNICALL
Java_com_pytron_shell_MainActivity_startPython(JNIEnv* env, jobject thiz, jstring homePath) {
    if (gMainActivity) env->DeleteGlobalRef(gMainActivity);
    gMainActivity = env->NewGlobalRef(thiz);

    const char* path = env->GetStringUTFChars(homePath, 0);
    LOGI("Starting Python configuration with home: %s", path);

    // ==========================================================
    // 1. FIX FILE DESCRIPTORS (THE CRITICAL FIX)
    // Python crashes if fd 0, 1, 2 are closed/invalid. We point them to /dev/null.
    // ==========================================================
    int fd = open("/dev/null", O_RDWR);
    if (fd != -1) {
        dup2(fd, 0); // stdin
        dup2(fd, 1); // stdout
        dup2(fd, 2); // stderr
        if (fd > 2) close(fd);
    }
    // ==========================================================

    // 2. ENVIRONMENT SETUP
    setenv("PYTHONHOME", path, 1);
    setenv("PYTHONUNBUFFERED", "1", 1); // Disable buffering
    setenv("PYTHON_PLATFORM","android",1);
    std::string base = std::string(path);
    std::string libPath = base + "/Lib";
    std::string sitePath = base + "/site-packages";
    std::string zipPath = base + "/python314.zip";

    if (access(libPath.c_str(), F_OK) != -1) {
        LOGI("Native: Found Lib folder at %s", libPath.c_str());
    } else {
        LOGI("Native: Lib folder not found, assuming zip or custom structure.");
    }

    // DLOPEN
    // Use the specific version name to be safe
    void* handle = dlopen("libpython3.14.so", RTLD_NOW | RTLD_GLOBAL);
    if (!handle) LOGE("Could not dlopen libpython3.14.so: %s", dlerror());
    else LOGI("Successfully loaded libpython3.14.so globally");

    // --- CONFIGURATION ---
    PyStatus status;
    PyConfig config;
    PyConfig_InitIsolatedConfig(&config);

    // CRITICAL: Stop Python from trying to initialize C-level streams
    config.configure_c_stdio = 0;
    config.parse_argv = 0;
    // Optional: Stop Python from stealing signal handlers (Good for Android)
    config.install_signal_handlers = 0;

    wchar_t *wpath = Py_DecodeLocale(path, NULL);
    status = PyConfig_SetString(&config, &config.program_name, wpath);
    status = PyConfig_SetString(&config, &config.home, wpath);

    // MODULE SEARCH PATHS
    config.module_search_paths_set = 1;

    wchar_t *wBase = Py_DecodeLocale(base.c_str(), NULL);
    wchar_t *wLib = Py_DecodeLocale(libPath.c_str(), NULL);
    wchar_t *wSite = Py_DecodeLocale(sitePath.c_str(), NULL);
    wchar_t *wZip = Py_DecodeLocale(zipPath.c_str(), NULL);

    PyWideStringList_Append(&config.module_search_paths, wBase);
    PyWideStringList_Append(&config.module_search_paths, wLib);

    // Lib-dynload (Critical for .so extensions like _struct)
    std::string dynPath = libPath + "/lib-dynload";
    wchar_t *wDyn = Py_DecodeLocale(dynPath.c_str(), NULL);
    PyWideStringList_Append(&config.module_search_paths, wDyn);

    PyWideStringList_Append(&config.module_search_paths, wZip);
    PyWideStringList_Append(&config.module_search_paths, wSite);

    // Register embedded module
    if (PyImport_AppendInittab("_pytron_android", PyInit__pytron_android) == -1) {
        LOGE("Failed to add _pytron_android to builtins");
    }

    LOGI("Calling Py_InitializeFromConfig...");
    status = Py_InitializeFromConfig(&config);

    if (PyStatus_Exception(status)) {
        LOGE("FATAL: Py_InitializeFromConfig failed.");
        if (status.err_msg) LOGE("Python Config Error: %s", status.err_msg);
        if (PyErr_Occurred()) PyErr_Print();
    } else {
        LOGI("Py_Initialize success!");

        // Run Main
        // We override sys.stdout/stderr here so print() goes to LogCat
        std::string runCmd =
            "import sys\n"
            "class LogCatOut:\n"
            "    def write(self, s):\n"
            "        import _pytron_android, json\n"
            "        if s.strip(): _pytron_android.send_to_android(json.dumps({'method': 'log', 'args': {'message': s.strip()}}))\n"
            "    def flush(self): pass\n"
            "sys.stdout = LogCatOut()\n"
            "sys.stderr = LogCatOut()\n"
            "try:\n"
            "    print('Native: sys.path is ' + str(sys.path))\n"
            "    import main\n"
            "    if hasattr(main, 'main'): main.main()\n"
            "except Exception as e:\n"
            "    import traceback\n"
            "    traceback.print_exc()\n"
            "    err_msg = 'Python Crash: ' + str(e)\n"
            "    import _pytron_android\n"
            "    import json\n"
            "    _pytron_android.send_to_android(json.dumps({'method': 'message_box', 'args': {'title': 'Crash', 'message': err_msg}}))\n";

        PyRun_SimpleString(runCmd.c_str());
    }

    PyConfig_Clear(&config);
    env->ReleaseStringUTFChars(homePath, path);
    PyMem_Free(wpath);
    PyMem_Free(wBase);
    PyMem_Free(wLib);
    PyMem_Free(wSite);
    PyMem_Free(wZip);
    PyMem_Free(wDyn);
}

extern "C" JNIEXPORT void JNICALL
Java_com_pytron_shell_MainActivity_sendToPython(JNIEnv* env, jobject thiz, jstring message) {
    if (!Py_IsInitialized()) return;
    PyGILState_STATE gstate = PyGILState_Ensure();
    const char* msg = env->GetStringUTFChars(message, 0);
    
    // LOGI("Received message for Python: %s", msg);

    // Call pytron.bindings.dispatch_android_message(msg)
    PyObject* bindings = PyImport_ImportModule("pytron.bindings");
    if (bindings) {
        PyObject* func = PyObject_GetAttrString(bindings, "dispatch_android_message");
        if (func && PyCallable_Check(func)) {
            PyObject* args = PyTuple_Pack(1, PyUnicode_FromString(msg));
            PyObject* result = PyObject_CallObject(func, args);
            Py_XDECREF(result);
            Py_DECREF(args);
            Py_DECREF(func);
        } else {
             if (PyErr_Occurred()) PyErr_Print();
             LOGE("Could not find dispatch_android_message in pytron.bindings");
        }
        Py_DECREF(bindings);
    } else {
         if (PyErr_Occurred()) PyErr_Print();
         LOGE("Could not import pytron.bindings");
    }

    env->ReleaseStringUTFChars(message, msg);
    PyGILState_Release(gstate);
}

extern "C" JNIEXPORT jint JNICALL JNI_OnLoad(JavaVM* vm, void* reserved) {
    gJavaVM = vm;
    return JNI_VERSION_1_6;
}