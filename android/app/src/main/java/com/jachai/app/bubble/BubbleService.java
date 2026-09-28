package com.jachai.app.bubble;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.graphics.Bitmap;
import android.graphics.PixelFormat;
import android.hardware.display.DisplayManager;
import android.hardware.display.VirtualDisplay;
import android.media.Image;
import android.media.ImageReader;
import android.media.projection.MediaProjection;
import android.media.projection.MediaProjectionManager;
import android.net.Uri;
import android.os.Build;
import android.os.Handler;
import android.os.HandlerThread;
import android.os.IBinder;
import android.os.Looper;
import android.os.SystemClock;
import android.util.DisplayMetrics;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.View;
import android.view.ViewConfiguration;
import android.view.WindowManager;
import android.widget.ImageView;
import android.widget.Toast;

import androidx.annotation.Nullable;
import androidx.core.app.NotificationCompat;
import androidx.core.app.ServiceCompat;
import androidx.core.content.FileProvider;
import androidx.core.content.IntentCompat;

import com.jachai.app.R;
import com.jachai.app.VerdictActivity;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.nio.ByteBuffer;

/**
 * SMOKE & MIRRORS fallback entry point for posts that can't be shared (e.g. private Facebook posts):
 * a draggable bubble over other apps. Tap → hide bubble → grab the current screen → VerdictActivity.
 *
 * One MediaProjection session per bubble session (Android 14+ allows one virtual display per consent), so the
 * virtual display runs continuously and we keep only the most recent frame.
 */
public class BubbleService extends Service {
    public static final String EXTRA_RESULT_CODE = "result_code";
    public static final String EXTRA_RESULT_DATA = "result_data";
    public static final String ACTION_STOP = "com.jachai.app.bubble.STOP";

    private static final String CHANNEL_ID = "bubble";
    private static final int NOTIFICATION_ID = 42;
    private static final long HIDE_BEFORE_CAPTURE_MS = 300;
    private static final long LONG_PRESS_CLOSE_MS = 800;

    private static volatile boolean running;

    public static boolean isRunning() {
        return running;
    }

    private final Handler main = new Handler(Looper.getMainLooper());
    private WindowManager windowManager;
    private ImageView bubble;
    private WindowManager.LayoutParams bubbleParams;
    private int screenWidth, screenHeight, bubbleSize;

    private MediaProjection projection;
    private VirtualDisplay virtualDisplay;
    private ImageReader imageReader;
    private HandlerThread captureThread;
    private Handler captureHandler;
    private final Object frameLock = new Object();
    private Image latestFrame;

    @Override
    public void onCreate() {
        super.onCreate();
        windowManager = getSystemService(WindowManager.class);
        DisplayMetrics dm = new DisplayMetrics();
        //noinspection deprecation — getRealMetrics is the simplest full-screen size that works back to API 24
        windowManager.getDefaultDisplay().getRealMetrics(dm);
        screenWidth = dm.widthPixels;
        screenHeight = dm.heightPixels;
        bubbleSize = Math.round(60 * dm.density);
    }

    @Nullable
    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent == null || ACTION_STOP.equals(intent.getAction())) {
            stopSelf();
            return START_NOT_STICKY;
        }
        if (running) return START_NOT_STICKY;

        // Android 14+: must be in the foreground (type mediaProjection) before getMediaProjection().
        startInForeground();
        int resultCode = intent.getIntExtra(EXTRA_RESULT_CODE, Activity.RESULT_CANCELED);
        Intent data = IntentCompat.getParcelableExtra(intent, EXTRA_RESULT_DATA, Intent.class);
        try {
            startProjection(resultCode, data);
            showBubble();
            running = true;
        } catch (RuntimeException e) {
            Toast.makeText(this, R.string.toast_capture_failed, Toast.LENGTH_LONG).show();
            stopSelf();
        }
        return START_NOT_STICKY;
    }

    @Override
    public void onDestroy() {
        running = false;
        main.removeCallbacksAndMessages(null);
        if (bubble != null) {
            try {
                windowManager.removeView(bubble);
            } catch (IllegalArgumentException ignored) {
                // already removed
            }
            bubble = null;
        }
        if (virtualDisplay != null) virtualDisplay.release();
        if (imageReader != null) imageReader.close();
        synchronized (frameLock) {
            if (latestFrame != null) latestFrame.close();
            latestFrame = null;
        }
        if (projection != null) projection.stop();
        if (captureThread != null) captureThread.quitSafely();
        super.onDestroy();
    }

    // ---------------------------------------------------------------- foreground + projection

    private void startInForeground() {
        NotificationManager nm = getSystemService(NotificationManager.class);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            nm.createNotificationChannel(new NotificationChannel(
                    CHANNEL_ID, getString(R.string.bubble_channel), NotificationManager.IMPORTANCE_LOW));
        }
        PendingIntent stop = PendingIntent.getService(this, 0,
                new Intent(this, BubbleService.class).setAction(ACTION_STOP), PendingIntent.FLAG_IMMUTABLE);
        Notification notification = new NotificationCompat.Builder(this, CHANNEL_ID)
                .setSmallIcon(R.drawable.ic_launcher_foreground)
                .setContentTitle(getString(R.string.bubble_notification_title))
                .setContentText(getString(R.string.bubble_notification_text))
                .addAction(0, getString(R.string.bubble_stop), stop)
                .setOngoing(true)
                .build();
        int type = Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q ? ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION : 0;
        ServiceCompat.startForeground(this, NOTIFICATION_ID, notification, type);
    }

    private void startProjection(int resultCode, @Nullable Intent data) {
        if (data == null || resultCode != Activity.RESULT_OK) throw new IllegalStateException("no consent");
        MediaProjectionManager mpm = getSystemService(MediaProjectionManager.class);
        projection = mpm.getMediaProjection(resultCode, data);
        if (projection == null) throw new IllegalStateException("projection refused");

        // Required before createVirtualDisplay on Android 14+. Fires if the user stops sharing from the status bar.
        projection.registerCallback(new MediaProjection.Callback() {
            @Override
            public void onStop() {
                main.post(BubbleService.this::stopSelf);
            }
        }, main);

        captureThread = new HandlerThread("jachai-capture");
        captureThread.start();
        captureHandler = new Handler(captureThread.getLooper());

        imageReader = ImageReader.newInstance(screenWidth, screenHeight, PixelFormat.RGBA_8888, 3);
        imageReader.setOnImageAvailableListener(reader -> {
            Image image;
            try {
                image = reader.acquireLatestImage();
            } catch (IllegalStateException e) {
                return;  // buffers busy; the next frame will do
            }
            if (image == null) return;
            synchronized (frameLock) {
                if (latestFrame != null) latestFrame.close();
                latestFrame = image;
            }
        }, captureHandler);

        int densityDpi = getResources().getDisplayMetrics().densityDpi;
        virtualDisplay = projection.createVirtualDisplay("jachai-capture", screenWidth, screenHeight, densityDpi,
                DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR, imageReader.getSurface(), null, null);
    }

    // ---------------------------------------------------------------- bubble

    @SuppressLint("ClickableViewAccessibility")
    private void showBubble() {
        bubble = new ImageView(this);
        bubble.setImageResource(R.drawable.ic_launcher_foreground);
        bubble.setBackgroundResource(R.drawable.bubble_bg);
        bubble.setElevation(8 * getResources().getDisplayMetrics().density);
        bubble.setContentDescription(getString(R.string.bubble_notification_text));

        @SuppressWarnings("deprecation")
        int type = Build.VERSION.SDK_INT >= Build.VERSION_CODES.O
                ? WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
                : WindowManager.LayoutParams.TYPE_PHONE;
        bubbleParams = new WindowManager.LayoutParams(bubbleSize, bubbleSize, type,
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE, PixelFormat.TRANSLUCENT);
        bubbleParams.gravity = Gravity.TOP | Gravity.START;
        bubbleParams.x = screenWidth - bubbleSize;
        bubbleParams.y = screenHeight / 3;

        final int touchSlop = ViewConfiguration.get(this).getScaledTouchSlop();
        bubble.setOnTouchListener(new View.OnTouchListener() {
            private int startX, startY;
            private float downRawX, downRawY;
            private long downAt;
            private boolean dragged;

            @Override
            public boolean onTouch(View v, MotionEvent e) {
                switch (e.getActionMasked()) {
                    case MotionEvent.ACTION_DOWN:
                        startX = bubbleParams.x;
                        startY = bubbleParams.y;
                        downRawX = e.getRawX();
                        downRawY = e.getRawY();
                        downAt = SystemClock.uptimeMillis();
                        dragged = false;
                        return true;
                    case MotionEvent.ACTION_MOVE:
                        float dx = e.getRawX() - downRawX, dy = e.getRawY() - downRawY;
                        if (Math.abs(dx) > touchSlop || Math.abs(dy) > touchSlop) dragged = true;
                        if (dragged) {
                            bubbleParams.x = startX + (int) dx;
                            bubbleParams.y = startY + (int) dy;
                            windowManager.updateViewLayout(bubble, bubbleParams);
                        }
                        return true;
                    case MotionEvent.ACTION_UP:
                        if (dragged) {
                            // Snap to the nearest side edge.
                            bubbleParams.x = bubbleParams.x + bubbleSize / 2 < screenWidth / 2 ? 0 : screenWidth - bubbleSize;
                            windowManager.updateViewLayout(bubble, bubbleParams);
                        } else if (SystemClock.uptimeMillis() - downAt > LONG_PRESS_CLOSE_MS) {
                            Toast.makeText(BubbleService.this, R.string.toast_bubble_closed, Toast.LENGTH_SHORT).show();
                            stopSelf();
                        } else {
                            captureScreen();
                        }
                        return true;
                    default:
                        return false;
                }
            }
        });
        windowManager.addView(bubble, bubbleParams);
    }

    // ---------------------------------------------------------------- capture

    private void captureScreen() {
        bubble.setVisibility(View.INVISIBLE);  // hiding it also forces a fresh frame without the bubble
        captureHandler.postDelayed(() -> {
            File file = null;
            synchronized (frameLock) {
                if (latestFrame != null) {
                    try {
                        file = saveJpeg(toBitmap(latestFrame));
                    } catch (IOException | RuntimeException ignored) {
                        file = null;
                    } finally {
                        latestFrame.close();
                        latestFrame = null;
                    }
                }
            }
            final File captured = file;
            main.post(() -> {
                if (bubble != null) bubble.setVisibility(View.VISIBLE);
                if (captured == null) {
                    Toast.makeText(this, R.string.toast_capture_failed, Toast.LENGTH_SHORT).show();
                } else {
                    openVerdict(captured);
                }
            });
        }, HIDE_BEFORE_CAPTURE_MS);
    }

    private Bitmap toBitmap(Image image) {
        Image.Plane plane = image.getPlanes()[0];
        ByteBuffer buffer = plane.getBuffer();
        int width = image.getWidth(), height = image.getHeight();
        int pixelStride = plane.getPixelStride();
        int rowPadding = plane.getRowStride() - pixelStride * width;
        Bitmap padded = Bitmap.createBitmap(width + rowPadding / pixelStride, height, Bitmap.Config.ARGB_8888);
        padded.copyPixelsFromBuffer(buffer);
        Bitmap exact = Bitmap.createBitmap(padded, 0, 0, width, height);
        if (exact != padded) padded.recycle();
        return exact;
    }

    private File saveJpeg(Bitmap bitmap) throws IOException {
        File dir = new File(getCacheDir(), "captures");
        File[] old = dir.listFiles();
        if (old != null) for (File f : old) //noinspection ResultOfMethodCallIgnored
            f.delete();
        if (!dir.exists() && !dir.mkdirs()) throw new IOException("cannot create " + dir);
        File file = new File(dir, "screen_" + System.currentTimeMillis() + ".jpg");
        try (FileOutputStream out = new FileOutputStream(file)) {
            bitmap.compress(Bitmap.CompressFormat.JPEG, 92, out);
        } finally {
            bitmap.recycle();
        }
        return file;
    }

    private void openVerdict(File file) {
        Uri uri = FileProvider.getUriForFile(this, getPackageName() + ".files", file);
        // Same entry point as the share sheet. Allowed from the background because our overlay is visible.
        startActivity(new Intent(Intent.ACTION_SEND)
                .setClass(this, VerdictActivity.class)
                .setType("image/jpeg")
                .putExtra(Intent.EXTRA_STREAM, uri)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_GRANT_READ_URI_PERMISSION));
    }
}
