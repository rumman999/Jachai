package com.jachai.app;

import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.widget.EditText;
import android.widget.TextView;
import android.widget.Toast;

import androidx.activity.EdgeToEdge;
import androidx.activity.result.ActivityResultLauncher;
import androidx.activity.result.PickVisualMediaRequest;
import androidx.activity.result.contract.ActivityResultContracts;
import androidx.annotation.NonNull;
import androidx.appcompat.app.AppCompatActivity;

import com.jachai.app.api.ApiClient;
import com.jachai.app.api.ApiModels;

import retrofit2.Call;
import retrofit2.Callback;
import retrofit2.Response;

/**
 * Home screen. The judged flow is the share sheet; this screen exists for setup and as a backup entry point:
 * server URL + health check, paste-a-claim, and pick-a-photo/video (useful on emulators).
 */
public class MainActivity extends AppCompatActivity {

    private EditText serverUrl, claimText;
    private TextView serverStatus;

    private final ActivityResultLauncher<PickVisualMediaRequest> pickMedia =
            registerForActivityResult(new ActivityResultContracts.PickVisualMedia(), this::onMediaPicked);

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        EdgeToEdge.enable(this);
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);
        Insets.padForSystemBars(findViewById(R.id.scroll));

        serverUrl = findViewById(R.id.server_url);
        claimText = findViewById(R.id.claim_text);
        serverStatus = findViewById(R.id.server_status);

        serverUrl.setText(ApiClient.getBaseUrl(this));
        findViewById(R.id.btn_save_server).setOnClickListener(v -> saveServerAndCheck());
        findViewById(R.id.btn_check_text).setOnClickListener(v -> checkText());
        findViewById(R.id.btn_pick_media).setOnClickListener(v -> pickMedia.launch(
                new PickVisualMediaRequest.Builder()
                        .setMediaType(ActivityResultContracts.PickVisualMedia.ImageAndVideo.INSTANCE)
                        .build()));

        checkHealth();
    }

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
