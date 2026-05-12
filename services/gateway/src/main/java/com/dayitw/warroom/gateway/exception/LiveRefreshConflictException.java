package com.dayitw.warroom.gateway.exception;

import com.fasterxml.jackson.databind.JsonNode;

/**
 * Feature 010 FR-016：005 POST /api/v1/episodes/live/refresh 回 409 時攜帶完整 body
 * （detail / running_pid / running_started_at / poll_status_url）。Gateway 必須將
 * body verbatim 透傳給前端，**不**走 GlobalExceptionHandler 的 ErrorResponseDto
 * 重映射 — 否則 running_pid 等欄位會遺失。
 *
 * Controller 攔住此 exception 後直接 ResponseEntity.status(409).body(payload())。
 */
public class LiveRefreshConflictException extends RuntimeException {

    private final transient JsonNode payload;

    public LiveRefreshConflictException(JsonNode payload) {
        super("live refresh conflict (409 from inference service)");
        this.payload = payload;
    }

    public JsonNode payload() {
        return payload;
    }
}
