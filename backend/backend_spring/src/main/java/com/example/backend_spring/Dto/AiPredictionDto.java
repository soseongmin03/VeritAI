package com.example.backend_spring.Dto;

public class AiPredictionDto {

    private boolean isDeepfake;
    private double confidence;
    private int faceCount;
    private boolean watermarkDetected;
    private String modelVersion;
    private long processingTimeMs;
    private String message;

    public boolean isDeepfake() {
        return isDeepfake;
    }

    public void setDeepfake(boolean deepfake) {
        isDeepfake = deepfake;
    }

    public double getConfidence() {
        return confidence;
    }

    public void setConfidence(double confidence) {
        this.confidence = confidence;
    }

    public int getFaceCount() {
        return faceCount;
    }

    public void setFaceCount(int faceCount) {
        this.faceCount = faceCount;
    }

    public boolean isWatermarkDetected() {
        return watermarkDetected;
    }

    public void setWatermarkDetected(boolean watermarkDetected) {
        this.watermarkDetected = watermarkDetected;
    }

    public String getModelVersion() {
        return modelVersion;
    }

    public void setModelVersion(String modelVersion) {
        this.modelVersion = modelVersion;
    }

    public long getProcessingTimeMs() {
        return processingTimeMs;
    }

    public void setProcessingTimeMs(long processingTimeMs) {
        this.processingTimeMs = processingTimeMs;
    }

    public String getMessage() {
        return message;
    }

    public void setMessage(String message) {
        this.message = message;
    }
}