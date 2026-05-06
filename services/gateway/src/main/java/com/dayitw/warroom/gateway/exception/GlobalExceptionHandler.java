package com.dayitw.warroom.gateway.exception;

import com.dayitw.warroom.gateway.dto.ErrorCode;
import com.dayitw.warroom.gateway.dto.ErrorResponseDto;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import java.util.UUID;

@RestControllerAdvice
public class GlobalExceptionHandler {

    private static final Logger log = LoggerFactory.getLogger(GlobalExceptionHandler.class);
    public static final String REQUEST_ID_MDC = "requestId";

    @ExceptionHandler(InferenceBusyException.class)
    public ResponseEntity<ErrorResponseDto> handleBusy(InferenceBusyException ex) {
        log.warn("inference.busy requestId={} message={}", currentRequestId(), ex.getMessage());
        return build(HttpStatus.CONFLICT, ErrorCode.InferenceBusy,
                "Inference service is currently processing another request");
    }

    @ExceptionHandler(InferenceTimeoutException.class)
    public ResponseEntity<ErrorResponseDto> handleTimeout(InferenceTimeoutException ex) {
        log.warn("inference.timeout requestId={} message={}", currentRequestId(), ex.getMessage());
        return build(HttpStatus.GATEWAY_TIMEOUT, ErrorCode.InferenceTimeout,
                "Inference service did not respond in time");
    }

    @ExceptionHandler(PredictionNotReadyException.class)
    public ResponseEntity<ErrorResponseDto> handleNotReady(PredictionNotReadyException ex) {
        log.info("inference.not_ready requestId={} message={}", currentRequestId(), ex.getMessage());
        return build(HttpStatus.NOT_FOUND, ErrorCode.PredictionNotReady,
                "No prediction available yet");
    }

    @ExceptionHandler(InferenceServiceException.class)
    public ResponseEntity<ErrorResponseDto> handleService(InferenceServiceException ex) {
        log.error("inference.unavailable requestId={} message={}", currentRequestId(), ex.getMessage());
        return build(HttpStatus.SERVICE_UNAVAILABLE, ErrorCode.InferenceServiceUnavailable,
                "Inference service is unavailable");
    }

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<ErrorResponseDto> handleBadRequest(IllegalArgumentException ex) {
        log.warn("bad.request requestId={} message={}", currentRequestId(), ex.getMessage());
        return build(HttpStatus.BAD_REQUEST, ErrorCode.BadRequest, ex.getMessage());
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<ErrorResponseDto> handleAny(Exception ex) {
        log.error("internal.error requestId={} errorClass={}",
                currentRequestId(), ex.getClass().getName(), ex);
        return build(HttpStatus.INTERNAL_SERVER_ERROR, ErrorCode.InternalServerError,
                "Unexpected internal error");
    }

    private static ResponseEntity<ErrorResponseDto> build(HttpStatus status, ErrorCode code, String message) {
        return ResponseEntity.status(status).body(ErrorResponseDto.of(code, message, currentRequestId()));
    }

    private static String currentRequestId() {
        String id = MDC.get(REQUEST_ID_MDC);
        return id != null ? id : UUID.randomUUID().toString();
    }
}
