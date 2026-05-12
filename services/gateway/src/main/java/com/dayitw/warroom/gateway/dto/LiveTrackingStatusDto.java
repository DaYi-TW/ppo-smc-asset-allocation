package com.dayitw.warroom.gateway.dto;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonProperty;

/**
 * Pass-through DTO mirroring 005 LiveTrackingStatusResponse schema (feature 010 FR-015 / FR-027).
 * Field names use snake_case to match 005 FastAPI response — Jackson @JsonProperty 對應。
 */
@JsonInclude(JsonInclude.Include.ALWAYS)
public record LiveTrackingStatusDto(
        @JsonProperty("last_updated") String lastUpdated,
        @JsonProperty("last_frame_date") String lastFrameDate,
        @JsonProperty("data_lag_days") Integer dataLagDays,
        @JsonProperty("is_running") boolean isRunning,
        @JsonProperty("last_error") String lastError
) {
}
