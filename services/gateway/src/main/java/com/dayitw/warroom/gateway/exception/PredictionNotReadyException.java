package com.dayitw.warroom.gateway.exception;

public class PredictionNotReadyException extends InferenceServiceException {
    public PredictionNotReadyException(String message) {
        super(message);
    }
}
