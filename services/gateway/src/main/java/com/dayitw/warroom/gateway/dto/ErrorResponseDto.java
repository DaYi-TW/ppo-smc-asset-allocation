package com.dayitw.warroom.gateway.dto;

import com.fasterxml.jackson.annotation.JsonInclude;

import java.util.Map;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record ErrorResponseDto(
        String error,
        String message,
        String requestId,
        Map<String, Object> details
) {
    public static ErrorResponseDto of(ErrorCode code, String message, String requestId) {
        return new ErrorResponseDto(code.name(), message, requestId, null);
    }
}
