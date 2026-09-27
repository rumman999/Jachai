package com.jachai.app.api;

import android.content.Context;
import android.content.SharedPreferences;

import androidx.annotation.Nullable;

import com.jachai.app.BuildConfig;

import java.util.concurrent.TimeUnit;

import okhttp3.HttpUrl;
import okhttp3.OkHttpClient;
import okhttp3.logging.HttpLoggingInterceptor;
import retrofit2.Retrofit;
import retrofit2.converter.gson.GsonConverterFactory;

/** Builds the Retrofit service. Base URL = runtime override (home screen) or the one baked in at build time. */
public final class ApiClient {
    private static final String PREFS = "jachai";
    private static final String KEY_BASE_URL = "base_url";

    private static ApiService service;
    private static String serviceUrl;

    private ApiClient() {}

    public static synchronized ApiService get(Context context) {
        String url = getBaseUrl(context);
        if (service == null || !url.equals(serviceUrl)) {
            HttpLoggingInterceptor logging = new HttpLoggingInterceptor();
            logging.setLevel(BuildConfig.DEBUG ? HttpLoggingInterceptor.Level.BASIC : HttpLoggingInterceptor.Level.NONE);
            OkHttpClient http = new OkHttpClient.Builder()
                    .connectTimeout(15, TimeUnit.SECONDS)
                    .writeTimeout(60, TimeUnit.SECONDS)   // video uploads on mobile data
                    .readTimeout(30, TimeUnit.SECONDS)
                    .addInterceptor(logging)
                    .build();
            service = new Retrofit.Builder()
                    .baseUrl(url)
                    .client(http)
                    .addConverterFactory(GsonConverterFactory.create())
                    .build()
                    .create(ApiService.class);
            serviceUrl = url;
        }
        return service;
    }

    public static String getBaseUrl(Context context) {
        String saved = prefs(context).getString(KEY_BASE_URL, null);
        String url = normalize(saved != null ? saved : BuildConfig.API_BASE_URL);
        return url != null ? url : BuildConfig.API_BASE_URL;
    }

    /** Saves a runtime override. Returns false if the URL is not valid. Empty string resets to the build default. */
    public static boolean setBaseUrl(Context context, String raw) {
        if (raw == null || raw.trim().isEmpty()) {
            prefs(context).edit().remove(KEY_BASE_URL).apply();
            return true;
        }
        String url = normalize(raw);
        if (url == null) return false;
        prefs(context).edit().putString(KEY_BASE_URL, url).apply();
        return true;
    }

    @Nullable
    static String normalize(String raw) {
        String url = raw.trim();
        if (!url.startsWith("http://") && !url.startsWith("https://")) url = "https://" + url;
        if (!url.endsWith("/")) url += "/";
        return HttpUrl.parse(url) != null ? url : null;
    }

    private static SharedPreferences prefs(Context context) {
        return context.getApplicationContext().getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }
}
