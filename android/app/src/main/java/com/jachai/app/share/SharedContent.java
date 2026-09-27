package com.jachai.app.share;

import android.content.ClipData;
import android.content.Context;
import android.content.Intent;
import android.net.Uri;

import androidx.annotation.Nullable;
import androidx.core.content.IntentCompat;

import java.util.ArrayList;

/**
 * Normalises whatever the share sheet hands us. Apps disagree on where they put things:
 * WhatsApp/Gallery use EXTRA_STREAM, some apps only fill ClipData, Facebook often shares text with a link.
 */
public final class SharedContent {
    public final Uri uri;
    public final String mimeType;
    public final String text;
    public final boolean hadMultiple;

    private SharedContent(Uri uri, String mimeType, String text, boolean hadMultiple) {
        this.uri = uri;
        this.mimeType = mimeType;
        this.text = text;
        this.hadMultiple = hadMultiple;
    }

    public boolean isText() {
        return text != null;
    }

    public boolean isVideo() {
        return mimeType != null && mimeType.startsWith("video/");
    }

    public boolean isSupportedMedia() {
        return mimeType != null && (mimeType.startsWith("image/") || mimeType.startsWith("video/"));
    }

    @Nullable
    public static SharedContent from(Context context, @Nullable Intent intent) {
        if (intent == null) return null;
        String action = intent.getAction();
        String type = intent.getType();
        boolean multiple = Intent.ACTION_SEND_MULTIPLE.equals(action);
        if (!Intent.ACTION_SEND.equals(action) && !multiple) return null;

        // Plain text share: prefer the text even if the app also attached a preview image.
        String text = extractText(intent);
        if (type != null && type.startsWith("text/") && text != null) {
            return new SharedContent(null, "text/plain", text, false);
        }

        Uri uri = null;
        boolean hadMultiple = false;
        if (multiple) {
            ArrayList<Uri> uris = IntentCompat.getParcelableArrayListExtra(intent, Intent.EXTRA_STREAM, Uri.class);
            if (uris != null && !uris.isEmpty()) {
                uri = uris.get(0);
                hadMultiple = uris.size() > 1;
            }
        } else {
            uri = IntentCompat.getParcelableExtra(intent, Intent.EXTRA_STREAM, Uri.class);
        }
        ClipData clip = intent.getClipData();
        if (uri == null && clip != null && clip.getItemCount() > 0) {
            uri = clip.getItemAt(0).getUri();
            hadMultiple = clip.getItemCount() > 1;
        }

        if (uri != null) {
            String mime = null;
            try {
                mime = context.getContentResolver().getType(uri);
            } catch (SecurityException ignored) {
                // fall through to the intent's declared type
            }
            if (mime == null || mime.equals("*/*") || mime.equals("application/octet-stream")) mime = type;
            return new SharedContent(uri, mime, null, hadMultiple);
        }
        return text != null ? new SharedContent(null, "text/plain", text, false) : null;
    }

    @Nullable
    private static String extractText(Intent intent) {
        CharSequence body = intent.getCharSequenceExtra(Intent.EXTRA_TEXT);
        if (body == null && intent.getClipData() != null && intent.getClipData().getItemCount() > 0) {
            body = intent.getClipData().getItemAt(0).getText();
        }
        if (body == null || body.toString().trim().isEmpty()) return null;
        String subject = intent.getStringExtra(Intent.EXTRA_SUBJECT);
        String combined = body.toString().trim();
        if (subject != null && !subject.trim().isEmpty() && !combined.contains(subject.trim())) {
            combined = subject.trim() + "\n" + combined;
        }
        return combined;
    }
}
