package com.dayitw.warroom.gateway.dto;

public enum ErrorCode {
    InferenceServiceUnavailable,
    InferenceTimeout,
    InferenceBusy,
    PredictionNotReady,
    RedisUnavailable,
    BadRequest,
    InternalServerError
}
