package com.dayitw.warroom.gateway.exception;

public class InferenceTimeoutException extends InferenceServiceException {
    public InferenceTimeoutException(String message) {
        super(message);
    }
    public InferenceTimeoutException(String message, Throwable cause) {
        super(message, cause);
    }
}
