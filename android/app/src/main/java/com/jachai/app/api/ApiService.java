package com.jachai.app.api;

import okhttp3.MultipartBody;
import retrofit2.Call;
import retrofit2.http.Body;
import retrofit2.http.GET;
import retrofit2.http.Multipart;
import retrofit2.http.POST;
import retrofit2.http.Part;
import retrofit2.http.Path;

/** The locked Day-1 contract. See docs/API_CONTRACT.md. */
public interface ApiService {

    @GET("health")
    Call<ApiModels.Health> health();

    @Multipart
    @POST("verify/media")
    Call<ApiModels.JobCreated> verifyMedia(@Part MultipartBody.Part file);

    @POST("verify/text")
    Call<ApiModels.JobCreated> verifyText(@Body ApiModels.TextRequest body);

    @GET("result/{job_id}")
    Call<ApiModels.Result> result(@Path("job_id") String jobId);
}
