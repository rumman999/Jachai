package com.jachai.app;

import android.content.Intent;
import android.graphics.Color;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import android.view.View;
import android.widget.ImageView;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.widget.Toast;

import androidx.activity.EdgeToEdge;
import androidx.activity.SystemBarStyle;
import androidx.annotation.NonNull;
import androidx.annotation.StringRes;
import androidx.appcompat.app.AppCompatActivity;
import androidx.core.content.ContextCompat;

import com.google.android.material.button.MaterialButton;
import com.jachai.app.api.ApiClient;
import com.jachai.app.api.ApiModels;
import com.jachai.app.api.ApiService;
import com.jachai.app.share.SharedContent;
import com.jachai.app.share.UriFiles;

import java.io.File;
import java.io.IOException;
import java.net.ConnectException;
import java.net.SocketTimeoutException;
import java.net.UnknownHostException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import okhttp3.MediaType;
import okhttp3.MultipartBody;
import okhttp3.RequestBody;
import retrofit2.Call;
import retrofit2.Callback;
import retrofit2.Response;

/**
 * Share sheet → upload → poll /result every 1.5 s → full-screen red/green verdict.
 * States: loading, result, error. Never crashes on bad input; every failure lands on the error state.
 */
public class VerdictActivity extends AppCompatActivity {
    private static final long POLL_INTERVAL_MS = 1500;
    private static final long MAX_WAIT_MS = 25_000;
    private static final long TIP_INTERVAL_MS = 2200;
    private static final long MAX_UPLOAD_BYTES = 50L * 1024 * 1024;

    private final Handler handler = new Handler(Looper.getMainLooper());
    private final ExecutorService io = Executors.newSingleThreadExecutor();

    private ApiService api;
    private Call<?> inFlight;
    private String jobId;
    private long startedAt;
    private File tempFile;
    private int tipIndex;

    private View root, loadingGroup, resultGroup;
    private TextView loadingTip, titleBn, titleEn, explanationBn, explanationEn, confidenceLabel, detail;
    private ImageView icon;
    private ProgressBar confidenceBar;
    private MaterialButton retryButton;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        EdgeToEdge.enable(this, SystemBarStyle.dark(Color.TRANSPARENT), SystemBarStyle.dark(Color.TRANSPARENT));
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_verdict);
        Insets.padForSystemBars(findViewById(R.id.content));

        root = findViewById(R.id.root);
        loadingGroup = findViewById(R.id.loading_group);
        resultGroup = findViewById(R.id.result_group);
        loadingTip = findViewById(R.id.loading_tip);
        icon = findViewById(R.id.verdict_icon);
        titleBn = findViewById(R.id.verdict_title_bn);
        titleEn = findViewById(R.id.verdict_title_en);
        explanationBn = findViewById(R.id.explanation_bn);
        explanationEn = findViewById(R.id.explanation_en);
        confidenceBar = findViewById(R.id.confidence_bar);
        confidenceLabel = findViewById(R.id.confidence_label);
        detail = findViewById(R.id.detail);
        retryButton = findViewById(R.id.btn_retry);

        findViewById(R.id.btn_done).setOnClickListener(v -> finish());
        retryButton.setOnClickListener(v -> start(getIntent()));

        api = ApiClient.get(this);
        start(getIntent());
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        handler.removeCallbacksAndMessages(null);
        if (inFlight != null) inFlight.cancel();
        io.shutdownNow();
        deleteTempFile();
    }

    // ---------------------------------------------------------------- flow

    private void start(Intent intent) {
        showLoading();
        SharedContent content = SharedContent.from(this, intent);
        if (content == null) {
            showError(R.string.error_nothing_shared);
            return;
        }
        startedAt = SystemClock.elapsedRealtime();
        if (content.isText()) {
            submitText(content.text);
        } else if (!content.isSupportedMedia()) {
            showError(R.string.error_unsupported);
        } else {
            if (content.hadMultiple) Toast.makeText(this, R.string.toast_first_item_only, Toast.LENGTH_SHORT).show();
            submitMedia(content);
        }
    }

    private void submitText(String text) {
        Call<ApiModels.JobCreated> call = api.verifyText(new ApiModels.TextRequest(text));
        inFlight = call;
        call.enqueue(jobCallback);
    }

    private void submitMedia(SharedContent content) {
        io.execute(() -> {
            try {
                deleteTempFile();
                tempFile = UriFiles.copyToCache(this, content.uri, content.mimeType, MAX_UPLOAD_BYTES);
                String fallbackName = content.isVideo() ? "shared.mp4" : "shared.jpg";
                String name = UriFiles.displayName(this, content.uri, fallbackName);
                RequestBody body = RequestBody.create(tempFile, MediaType.parse(content.mimeType));
                MultipartBody.Part part = MultipartBody.Part.createFormData("file", name, body);
                runOnUiThread(() -> {
                    if (isFinishing() || isDestroyed()) return;
                    Call<ApiModels.JobCreated> call = api.verifyMedia(part);
                    inFlight = call;
                    call.enqueue(jobCallback);
                });
            } catch (UriFiles.TooLargeException e) {
                runOnUiThread(() -> showError(R.string.error_too_large));
            } catch (IOException | SecurityException e) {
                runOnUiThread(() -> showError(R.string.error_cannot_read));
            }
        });
    }

    private final Callback<ApiModels.JobCreated> jobCallback = new Callback<ApiModels.JobCreated>() {
        @Override
        public void onResponse(@NonNull Call<ApiModels.JobCreated> call, @NonNull Response<ApiModels.JobCreated> response) {
            if (isFinishing()) return;
            ApiModels.JobCreated job = response.body();
            if (!response.isSuccessful() || job == null || job.jobId == null) {
                showError(errorForHttp(response.code()));
                return;
            }
            jobId = job.jobId;
            handler.postDelayed(VerdictActivity.this::poll, job.pollAfterMs > 0 ? job.pollAfterMs : POLL_INTERVAL_MS);
        }

        @Override
        public void onFailure(@NonNull Call<ApiModels.JobCreated> call, @NonNull Throwable t) {
            if (!call.isCanceled() && !isFinishing()) showError(errorForThrowable(t));
        }
    };

    private void poll() {
        Call<ApiModels.Result> call = api.result(jobId);
        inFlight = call;
        call.enqueue(new Callback<ApiModels.Result>() {
            @Override
            public void onResponse(@NonNull Call<ApiModels.Result> call, @NonNull Response<ApiModels.Result> response) {
                if (isFinishing()) return;
                ApiModels.Result result = response.body();
                if (!response.isSuccessful() || result == null) {
                    showError(errorForHttp(response.code()));
                } else if (result.isFinished() && result.verdict != null) {
                    showResult(result);
                } else {
                    pollAgainOrGiveUp();
                }
            }

            @Override
            public void onFailure(@NonNull Call<ApiModels.Result> call, @NonNull Throwable t) {
                if (call.isCanceled() || isFinishing()) return;
                pollAgainOrGiveUp();  // a dropped poll on flaky Wi-Fi shouldn't kill the check
            }
        });
    }

    private void pollAgainOrGiveUp() {
        if (SystemClock.elapsedRealtime() - startedAt > MAX_WAIT_MS) {
            showError(R.string.error_timeout);
        } else {
            handler.postDelayed(this::poll, POLL_INTERVAL_MS);
        }
    }

    // ---------------------------------------------------------------- UI states

    private void showLoading() {
        handler.removeCallbacksAndMessages(null);
        setBackground(R.color.verdict_loading);
        loadingGroup.setVisibility(View.VISIBLE);
        resultGroup.setVisibility(View.GONE);
        tipIndex = 0;
        rotateTip();
    }

    private void rotateTip() {
        String[] tips = getResources().getStringArray(R.array.loading_tips);
        loadingTip.setText(tips[tipIndex++ % tips.length]);
        handler.postDelayed(this::rotateTip, TIP_INTERVAL_MS);
    }

    private void showResult(ApiModels.Result r) {
        handler.removeCallbacksAndMessages(null);
        deleteTempFile();
        boolean red = r.isRed();
        setBackground(red ? R.color.verdict_red : R.color.verdict_green);
        icon.setImageResource(red ? R.drawable.ic_verdict_fake : R.drawable.ic_verdict_real);

        titleBn.setText(r.title != null ? r.title.bn : getString(red ? R.string.fallback_red_bn : R.string.fallback_green_bn));
        titleEn.setText(r.title != null ? r.title.en : getString(red ? R.string.fallback_red_en : R.string.fallback_green_en));
        explanationBn.setText(r.explanation != null ? r.explanation.bn : "");
        explanationEn.setText(r.explanation != null ? r.explanation.en : "");

        int pct = r.confidence != null ? (int) Math.round(r.confidence * 100) : 0;
        confidenceBar.setVisibility(View.VISIBLE);
        confidenceLabel.setVisibility(View.VISIBLE);
        confidenceBar.setProgress(pct);
        confidenceLabel.setText(getString(R.string.confidence_fmt, pct));

        if (r.matchedClaim != null) {
            detail.setText(getString(R.string.matched_claim_fmt, r.matchedClaim.claimBn, r.matchedClaim.claimEn));
            detail.setVisibility(View.VISIBLE);
        } else {
            detail.setVisibility(View.GONE);
        }
        retryButton.setVisibility(View.GONE);
        showResultGroup();
    }

    private void showError(@StringRes int message) {
        handler.removeCallbacksAndMessages(null);
        setBackground(R.color.verdict_neutral);
        icon.setImageResource(R.drawable.ic_verdict_error);
        titleBn.setText(R.string.error_title_bn);
        titleEn.setText(R.string.error_title_en);
        String[] both = getString(message).split("\n", 2);
        explanationBn.setText(both[0]);
        explanationEn.setText(both.length > 1 ? both[1] : "");
        confidenceBar.setVisibility(View.GONE);
        confidenceLabel.setVisibility(View.GONE);
        detail.setVisibility(View.GONE);
        retryButton.setVisibility(View.VISIBLE);
        showResultGroup();
    }

    private void showResultGroup() {
        loadingGroup.setVisibility(View.GONE);
        resultGroup.setVisibility(View.VISIBLE);
        resultGroup.setAlpha(0f);
        resultGroup.animate().alpha(1f).setDuration(250).start();
    }

    private void setBackground(int colorRes) {
        root.setBackgroundColor(ContextCompat.getColor(this, colorRes));
    }

    // ---------------------------------------------------------------- errors

    @StringRes
    private static int errorForHttp(int code) {
        if (code == 413) return R.string.error_too_large;
        if (code == 415) return R.string.error_unsupported;
        if (code == 404) return R.string.error_expired;
        return R.string.error_server;
    }

    @StringRes
    private static int errorForThrowable(Throwable t) {
        if (t instanceof UnknownHostException || t instanceof ConnectException) return R.string.error_no_internet;
        if (t instanceof SocketTimeoutException) return R.string.error_timeout;
        return R.string.error_server;
    }

    private void deleteTempFile() {
        File f = tempFile;
        tempFile = null;
        //noinspection ResultOfMethodCallIgnored
        if (f != null) f.delete();
    }
}
