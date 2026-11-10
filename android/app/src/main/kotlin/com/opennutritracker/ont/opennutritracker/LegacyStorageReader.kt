package com.opennutritracker.ont.opennutritracker

import android.content.Context
import android.util.Base64
import java.security.KeyStore
import java.security.PrivateKey
import java.security.spec.MGF1ParameterSpec
import javax.crypto.Cipher
import javax.crypto.spec.GCMParameterSpec
import javax.crypto.spec.IvParameterSpec
import javax.crypto.spec.OAEPParameterSpec
import javax.crypto.spec.PSource

/** Read-only recovery of existing plugin ciphertext. Never creates/deletes a
 * legacy key, edits preferences, exports keys or turns off Hive validation. */
object LegacyStorageReader {
    private const val prefix = "VGhpcyBpcyB0aGUgcHJlZml4IGZvciBhIHNlY3VyZSBzdG9yYWdlCg_"
    fun read(context: Context, key: String): Map<String, Any?> {
        require(key == "HiveEncryptionTag" || key == "ActiveProfileTag" || key.startsWith("nutri-bridge-v1:"))
        val prefs = context.getSharedPreferences(if (key.startsWith("nutri-bridge-v1:")) "FlutterSecureStorage" else "SharedPrefs", Context.MODE_PRIVATE)
        val raw = prefs.getString(prefix + key, null) ?: return mapOf("present" to false, "value" to null)
        // Preserve encrypted material locally, outside Android's cloud backup.
        val backup = java.io.File(context.noBackupFilesDir, "legacy-storage-preserved")
        backup.mkdirs()
        java.io.File(context.applicationInfo.dataDir, "shared_prefs").listFiles()?.filter { it.extension == "xml" }?.forEach {
            val target = java.io.File(backup, it.name)
            if (!target.exists()) it.copyTo(target)
        }
        val payload = Base64.decode(raw, Base64.DEFAULT)
        val wrapped = context.getSharedPreferences("FlutterSecureKeyStorage", Context.MODE_PRIVATE).all.values.filterIsInstance<String>()
        val ks = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        val aliases = listOf(context.packageName + ".FlutterSecureStoragePluginKeyOAEP", context.packageName + ".FlutterSecureStoragePluginKey")
        for (alias in aliases) {
            if (!ks.containsAlias(alias)) continue
            val privateKey = ks.getKey(alias, null) as? PrivateKey ?: continue
            for (encoded in wrapped) {
                try {
                    val rsa = Cipher.getInstance(if (alias.endsWith("OAEP")) "RSA/ECB/OAEPPadding" else "RSA/ECB/PKCS1Padding", "AndroidKeyStoreBCWorkaround")
                    if (alias.endsWith("OAEP")) rsa.init(Cipher.UNWRAP_MODE, privateKey, OAEPParameterSpec("SHA-256", "MGF1", MGF1ParameterSpec.SHA1, PSource.PSpecified.DEFAULT))
                    else rsa.init(Cipher.UNWRAP_MODE, privateKey)
                    val aes = rsa.unwrap(Base64.decode(encoded, Base64.DEFAULT), "AES", Cipher.SECRET_KEY)
                    for (gcm in listOf(true, false)) {
                        try {
                            val ivSize = if (gcm) 12 else 16
                            if (payload.size <= ivSize) continue
                            val cipher = Cipher.getInstance(if (gcm) "AES/GCM/NoPadding" else "AES/CBC/PKCS7Padding")
                            val iv = payload.copyOfRange(0, ivSize)
                            if (gcm) cipher.init(Cipher.DECRYPT_MODE, aes, GCMParameterSpec(128, iv))
                            else cipher.init(Cipher.DECRYPT_MODE, aes, IvParameterSpec(iv))
                            val value = String(cipher.doFinal(payload.copyOfRange(ivSize, payload.size)), Charsets.UTF_8)
                            val valid = if (key == "HiveEncryptionTag") {
                                value.matches(Regex("[A-Za-z0-9_=-]{43,44}")) && Base64.decode(value, Base64.URL_SAFE).size == 32
                            } else if (key == "ActiveProfileTag") value.matches(Regex("[A-Za-z0-9:_-]{1,200}"))
                            else value.length <= 20000 && org.json.JSONObject(value).has("token")
                            if (valid) return mapOf("present" to true, "value" to value)
                        } catch (_: Exception) { /* Try another existing cipher; never reset. */ }
                    }
                } catch (_: Exception) { /* Try another existing wrapping key. */ }
            }
        }
        return mapOf("present" to true, "value" to null)
    }
}
