package com.dayitw.warroom.gateway.dto;

import com.fasterxml.jackson.annotation.JsonAlias;
import com.fasterxml.jackson.annotation.JsonInclude;

@JsonInclude(JsonInclude.Include.ALWAYS)
public record HealthDto(
        String status,
        @JsonAlias("uptime_seconds") int uptimeSeconds,
        @JsonAlias("policy_loaded") boolean policyLoaded,
        @JsonAlias("redis_reachable") boolean redisReachable,
        @JsonAlias("last_inference_at_utc") String lastInferenceAtUtc,
        @JsonAlias("next_scheduled_run_utc") String nextScheduledRunUtc
) {}
