package com.dayitw.warroom.gateway.dto;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonProperty;

/**
 * Pass-through DTO for 005 POST /api/v1/episodes/live/refresh 409 response (feature 010 SC-004).
 * 對應 OpenAPI RefreshConflictResponse schema。
 *
 * 重點：本 DTO **不**走 GlobalExceptionHandler 的 ErrorResponseDto 重映射 —
 * gateway 必須將 005 的 409 body verbatim 透傳給前端，前端 toast 直接讀
 * detail / running_pid / running_started_at（FR-016 對齊）。
 */
@JsonInclude(JsonInclude.Include.NON_ABSENT)
public record RefreshConflictDto(
        String detail,
        @JsonProperty("running_pid") int runningPid,
        @JsonProperty("running_started_at") String runningStartedAt,
        @JsonProperty("poll_status_url") String pollStatusUrl
) {
}
