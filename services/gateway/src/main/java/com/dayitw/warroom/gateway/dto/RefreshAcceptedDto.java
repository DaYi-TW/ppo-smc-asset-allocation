package com.dayitw.warroom.gateway.dto;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonProperty;

/**
 * Pass-through DTO for 005 POST /api/v1/episodes/live/refresh 202 response (feature 010 FR-016).
 * 對應 OpenAPI RefreshAcceptedResponse schema。
 */
@JsonInclude(JsonInclude.Include.NON_ABSENT)
public record RefreshAcceptedDto(
        boolean accepted,
        @JsonProperty("pipeline_id") String pipelineId,
        @JsonProperty("estimated_duration_seconds") int estimatedDurationSeconds,
        @JsonProperty("poll_status_url") String pollStatusUrl
) {
}
