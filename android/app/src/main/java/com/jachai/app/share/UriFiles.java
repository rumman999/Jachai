package com.jachai.app.share;

import android.content.Context;
import android.database.Cursor;
import android.net.Uri;
import android.provider.OpenableColumns;
import android.webkit.MimeTypeMap;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;

/** Copies a shared content:// Uri into our cache. The read grant from the sharing app can expire, a file can't. */
public final class UriFiles {
    private UriFiles() {}

    public static class TooLargeException extends IOException {
        public TooLargeException() {
            super("file too large");
        }
    }

    public static File copyToCache(Context context, Uri uri, String mimeType, long maxBytes) throws IOException {
        String ext = MimeTypeMap.getSingleton().getExtensionFromMimeType(mimeType);
        File out = File.createTempFile("shared_", "." + (ext != null ? ext : "bin"), context.getCacheDir());
        long total = 0;
        try (InputStream in = context.getContentResolver().openInputStream(uri);
             OutputStream os = new FileOutputStream(out)) {
            if (in == null) throw new IOException("cannot open " + uri);
            byte[] buf = new byte[64 * 1024];
            int n;
            while ((n = in.read(buf)) != -1) {
                total += n;
                if (total > maxBytes) throw new TooLargeException();
                os.write(buf, 0, n);
            }
        } catch (IOException | RuntimeException e) {
            //noinspection ResultOfMethodCallIgnored
            out.delete();
            throw e;
        }
        return out;
    }

    public static String displayName(Context context, Uri uri, String fallback) {
        try (Cursor c = context.getContentResolver().query(uri, new String[]{OpenableColumns.DISPLAY_NAME}, null, null, null)) {
            if (c != null && c.moveToFirst()) {
                String name = c.getString(0);
                if (name != null && !name.isEmpty()) return name;
            }
        } catch (RuntimeException ignored) {
            // some providers don't support the query
        }
        return fallback;
    }
}
