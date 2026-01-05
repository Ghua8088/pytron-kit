package com.pytron.shell

import android.app.Activity
import android.os.Bundle
import android.util.Log
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import org.json.JSONObject
import java.io.File
import java.io.FileInputStream
import java.io.FileOutputStream
import java.io.IOException
import java.util.zip.ZipEntry
import java.util.zip.ZipInputStream

class MainActivity : Activity() {

    private lateinit var webView: WebView

    companion object {
        init {
            // Load libffi first if it's separate, then your native lib
            try { System.loadLibrary("ffi") } catch (e: UnsatisfiedLinkError) { Log.w("Pytron", "libffi not found (might be static)") }
            System.loadLibrary("pytron-native")
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        Thread.setDefaultUncaughtExceptionHandler { thread, throwable ->
            Log.e("Pytron", "FATAL JAVA CRASH: ${throwable.message}", throwable)
        }

        webView = WebView(this)
        val settings = webView.settings
        settings.javaScriptEnabled = true
        settings.domStorageEnabled = true
        settings.allowFileAccess = true
        settings.allowFileAccessFromFileURLs = true
        settings.allowUniversalAccessFromFileURLs = true

        settings.allowUniversalAccessFromFileURLs = true

        // Enable Remote Debugging (Inspect via chrome://inspect)
        WebView.setWebContentsDebuggingEnabled(true)

        // 2. INJECT THE BRIDGE OBJECT
        // This allows JS to call window._pytron_bridge.postMessage("...")
        webView.addJavascriptInterface(AndroidBridgeInterface(), "_pytron_bridge")

        webView.webViewClient = object : WebViewClient() {
            override fun onPageFinished(view: WebView?, url: String?) {
                super.onPageFinished(view, url)
                Log.d("Pytron", "WebView loaded: $url")
                if (pendingScripts != null) {
                    val script = pendingScripts
                    // pendingScripts = null // Should we clear it? Usually yes, but depends if redirects happen.
                    // For now, let's keep it until next nav call or just execute.
                    view?.evaluateJavascript(script!!, null)
                }
            }
        }

        setContentView(webView)
        webView.loadUrl("file:///android_asset/www/index.html")

        // --- ASSET EXTRACTION LOGIC ---
        val pythonHome = File(filesDir, "python")
        
        Thread {
            try {
                // 1. Copy Assets (main.py, Lib/, site-packages/)
                Log.i("Pytron", "Checking/Copying python assets...")
                copyAssetFolder("python", pythonHome.absolutePath)

                Log.i("Pytron", "Starting Python Bridge...")
                startPython(pythonHome.absolutePath)

            } catch (e: Exception) {
                Log.e("Pytron", "Failed to start Python: ${e.message}", e)
            }
        }.start()
    }

    // --- NEW INNER CLASS ---
    inner class AndroidBridgeInterface {
        @android.webkit.JavascriptInterface
        fun postMessage(message: String) {
            // Forward the message from JS to our C++ Native Bridge
            // This eventually calls dispatch_android_message() in Python
            sendToPython(message)
        }
    }

    private fun copyAssetFolder(srcName: String, dstPath: String): Boolean {
        try {
            val fileList = assets.list(srcName) ?: return false
            if (fileList.isEmpty()) return true

            for (filename in fileList) {
                var inPath = if (srcName.isEmpty()) filename else srcName + File.separator + filename
                var outPath = dstPath + File.separator + filename

                // Check if it's a directory by trying to list its children
                // Note: assets.list returns empty array for both empty dir AND file.
                // We assume if it has an extension it's a file, or try to open it.
                var isDir = false
                val subFiles = assets.list(inPath)
                if (subFiles != null && subFiles.isNotEmpty()) {
                    isDir = true
                }

                if (isDir) {
                    File(outPath).mkdirs()
                    copyAssetFolder(inPath, outPath)
                } else {
                    // It's a file. Copy it.
                    copyAssetFile(inPath, outPath)
                }
            }
            return true
        } catch (e: Exception) {
            Log.e("Pytron", "Asset Copy Failed for $srcName", e)
            return false
        }
    }

    private fun copyAssetFile(srcPath: String, dstPath: String) {
        try {
            val dstFile = File(dstPath)
            
            // OPTIMIZATION: Don't copy if it already exists and has size
            // Note: For development, you might want to remove this check or add versioning
            // so updates get applied.
            // if (dstFile.exists() && dstFile.length() > 0) {
            //      // Log.d("Pytron", "Skipping existing file: $dstPath")
            //      return
            // }

            val inputStream = assets.open(srcPath)
            val outStream = FileOutputStream(dstFile)
            val buffer = ByteArray(64 * 1024) // 64KB buffer
            var read: Int
            while (inputStream.read(buffer).also { read = it } != -1) {
                outStream.write(buffer, 0, read)
            }
            inputStream.close()
            outStream.close()

            if (srcPath.endsWith(".zip")) {
                Log.i("Pytron", "SUCCESS: Copied $srcPath (Size: ${dstFile.length()})")
            }
        } catch (e: IOException) {
            // If it fails to open as a file, it might have been an empty directory caught in the loop
            // Log.w("Pytron", "Could not copy $srcPath (might be empty dir)")
        }
    }

    external fun startPython(homePath: String)
    external fun sendToPython(message: String)

    private var pendingScripts: String? = null

    fun onMessageFromPython(payload: String): String {
        runOnUiThread {
            try {
                // Log.d("Pytron", "Received from Python: $payload")
                val json = JSONObject(payload)
                val method = json.optString("method")
                val args = json.optJSONObject("args")

                if (method == "log") {
                    Log.i("PytronPython", args?.optString("message") ?: "")
                }
                else if (method == "message_box") {
                    val title = args?.optString("title")
                    val msg = args?.optString("message")
                    android.app.AlertDialog.Builder(this)
                        .setTitle(title)
                        .setMessage(msg)
                        .setPositiveButton("OK", null)
                        .show()
                }
                else if (method == "navigate") {
                    val url = args?.optString("url")
                    val scripts = args?.optString("scripts")
                    if (scripts != null) {
                         pendingScripts = scripts
                    }
                    if (url != null) {
                        webView.loadUrl(url)
                    }
                }
                else if (method == "eval") {
                    val code = args?.optString("code")
                    if (code != null) {
                        webView.evaluateJavascript(code, null)
                    }
                }
            } catch (e: Exception) {
                Log.e("Pytron", "Error processing message", e)
            }
        }
        return "{}"
    }
}
