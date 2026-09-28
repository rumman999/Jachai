package com.jachai.app;

import android.content.Intent;
import android.media.projection.MediaProjectionManager;
import android.net.Uri;
import android.os.Bundle;
import android.provider.Settings;
import android.widget.Button;
import android.widget.EditText;
import android.widget.TextView;
import android.widget.Toast;

import androidx.activity.EdgeToEdge;
import androidx.activity.result.ActivityResultLauncher;
import androidx.activity.result.PickVisualMediaRequest;
import androidx.activity.result.contract.ActivityResultContracts;
import androidx.annotation.NonNull;
import androidx.appcompat.app.AppCompatActivity;
import androidx.appcompat.app.AppCompatDelegate;
import androidx.core.content.ContextCompat;
import androidx.core.os.LocaleListCompat;
import androidx.core.splashscreen.SplashScreen;

import com.jachai.app.api.ApiClient;
import com.jachai.app.api.ApiModels;
import com.jachai.app.bubble.BubbleService;

import java.util.Locale;

import retrofit2.Call;
import retrofit2.Callback;
import retrofit2.Response;

/**
 * Home screen. The judged flow is the share sheet; this screen exists for setup and as a backup entry point:
 * paste-a-claim, pick-a-photo/video, the floating bubble, language toggle, and server URL + health check.
 */
public class MainActivity extends AppCompatActivity {

    private EditText serverUrl, claimText;
    private TextView serverStatus;
    private Button bubbleButton;

    private final ActivityResultLauncher<PickVisualMediaRequest> pickMedia =
            registerForActivityResult(new ActivityResultContracts.PickVisualMedia(), this::onMediaPicked);

    private final ActivityResultLauncher<Intent> screenCaptureConsent =
            registerForActivityResult(new ActivityResultContracts.StartActivityForResult(), result -> {
                if (result.getResultCode() != RESULT_OK || result.getData() == null) return;
                ContextCompat.startForegroundService(this, new Intent(this, BubbleService.class)
                        .putExtra(BubbleService.EXTRA_RESULT_CODE, result.getResultCode())
                        .putExtra(BubbleService.EXTRA_RESULT_DATA, result.getData()));
                Toast.makeText(this, R.string.toast_bubble_started, Toast.LENGTH_LONG).show();
                bubbleButton.setText(R.string.btn_bubble_stop);
                moveTaskToBack(true);  // get out of the way so the user can open the post
            });

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        SplashScreen.installSplashScreen(this);
        EdgeToEdge.enable(this);
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);
        Insets.padForSystemBars(findViewById(R.id.scroll));

        serverUrl = findViewById(R.id.server_url);
        claimText = findViewById(R.id.claim_text);
        serverStatus = findViewById(R.id.server_status);
        bubbleButton = findViewById(R.id.btn_bubble);

        serverUrl.setText(ApiClient.getBaseUrl(this));
        findViewById(R.id.btn_language).setOnClickListener(v -> toggleLanguage());
        findViewById(R.id.btn_save_server).setOnClickListener(v -> saveServerAndCheck());
        findViewById(R.id.btn_check_text).setOnClickListener(v -> checkText());
        findViewById(R.id.btn_pick_media).setOnClickListener(v -> pickMedia.launch(
                new PickVisualMediaRequest.Builder()
                        .setMediaType(ActivityResultContracts.PickVisualMedia.ImageAndVideo.INSTANCE)
                        .build()));
        bubbleButton.setOnClickListener(v -> toggleBubble());

        checkHealth();
    }

    @Override
    protected void onResume() {
        super.onResume();
        bubbleButton.setText(BubbleService.isRunning() ? R.string.btn_bubble_stop : R.string.btn_bubble_start);
    }

    // ---------------------------------------------------------------- language

    /** Follows the device language by default; this button is the manual override. */
    private void toggleLanguage() {
        LocaleListCompat current = AppCompatDelegate.getApplicationLocales();
        String language = current.isEmpty() ? Locale.getDefault().getLanguage() : current.get(0).getLanguage();
        AppCompatDelegate.setApplicationLocales(LocaleListCompat.forLanguageTags("bn".equals(language) ? "en" : "bn"));
    }

    // ---------------------------------------------------------------- bubble

    private void toggleBubble() {
        if (BubbleService.isRunning()) {
            startService(new Intent(this, BubbleService.class).setAction(BubbleService.ACTION_STOP));
            bubbleButton.setText(R.string.btn_bubble_start);
            return;
        }
        if (!Settings.canDrawOverlays(this)) {
            Toast.makeText(this, R.string.toast_overlay_permission, Toast.LENGTH_LONG).show();
            startActivity(new Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:" + getPackageName())));
            return;
        }
        MediaProjectionManager mpm = getSystemService(MediaProjectionManager.class);
        screenCaptureConsent.launch(mpm.createScreenCaptureIntent());
    }

    // ---------------------------------------------------------------- server

    private void saveServerAndCheck() {
        if (!ApiClient.setBaseUrl(this, serverUrl.getText().toString())) {
            serverStatus.setText(R.string.server_invalid_url);
            return;
        }
        serverUrl.setText(ApiClient.getBaseUrl(this));
        checkHealth();
    }

    private void checkHealth() {
        serverStatus.setText(R.string.server_checking);
        ApiClient.get(this).health().enqueue(new Callback<ApiModels.Health>() {
            @Override
            public void onResponse(@NonNull Call<ApiModels.Health> call, @NonNull Response<ApiModels.Health> response) {
                ApiModels.Health h = response.body();
                if (response.isSuccessful() && h != null && "ok".equals(h.status)) {
                    serverStatus.setText(getString(h.mockMode ? R.string.server_ok_mock : R.string.server_ok, h.version));
                } else {
                    serverStatus.setText(getString(R.string.server_error_code, response.code()));
                }
            }

            @Override
            public void onFailure(@NonNull Call<ApiModels.Health> call, @NonNull Throwable t) {
                serverStatus.setText(R.string.server_unreachable);
            }
        });
    }

    // ---------------------------------------------------------------- checks

    private void checkText() {
        String text = claimText.getText().toString().trim();
        if (text.isEmpty()) {
            Toast.makeText(this, R.string.toast_enter_text, Toast.LENGTH_SHORT).show();
            return;
        }
        // Same entry point as the share sheet, so this exercises exactly the judged code path.
        startActivity(new Intent(Intent.ACTION_SEND)
                .setClass(this, VerdictActivity.class)
                .setType("text/plain")
                .putExtra(Intent.EXTRA_TEXT, text));
    }

    private void onMediaPicked(Uri uri) {
        if (uri == null) return;
        String type = getContentResolver().getType(uri);
        startActivity(new Intent(Intent.ACTION_SEND)
                .setClass(this, VerdictActivity.class)
                .setType(type != null ? type : "image/*")
                .putExtra(Intent.EXTRA_STREAM, uri)
                .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION));
    }
}
