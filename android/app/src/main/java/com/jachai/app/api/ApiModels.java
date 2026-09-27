package com.jachai.app.api;

import com.google.gson.annotations.SerializedName;

public final class ApiModels {
    private ApiModels() {}

    public static class JobCreated {
        @SerializedName("job_id") public String jobId;
        public String status;
        @SerializedName("poll_after_ms") public int pollAfterMs;
    }

    public static class TextRequest {
        public final String text;

        public TextRequest(String text) {
            this.text = text;
        }
    }

    public static class Bilingual {
        public String en;
        public String bn;
    }

    public static class MatchedClaim {
        public String id;
        @SerializedName("claim_en") public String claimEn;
        @SerializedName("claim_bn") public String claimBn;
        public double similarity;
    }

    public static class Result {
        @SerializedName("job_id") public String jobId;
        public String status;
        public String kind;
        public String verdict;
        public String label;
        public Double confidence;
        @SerializedName("fake_probability") public Double fakeProbability;
        public Bilingual title;
        public Bilingual explanation;
        public String engine;
        @SerializedName("frames_analyzed") public Integer framesAnalyzed;
        @SerializedName("matched_claim") public MatchedClaim matchedClaim;
        @SerializedName("extracted_text") public String extractedText;
        @SerializedName("elapsed_ms") public Integer elapsedMs;

        public boolean isFinished() {
            return "done".equals(status) || "error".equals(status);
        }

        public boolean isRed() {
            return "red".equals(verdict);
        }
    }

    public static class Health {
        public String status;
        public String version;
        @SerializedName("mock_mode") public boolean mockMode;
    }
}
