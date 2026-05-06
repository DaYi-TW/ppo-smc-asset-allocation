package com.dayitw.warroom.gateway.dto;

import com.fasterxml.jackson.annotation.JsonAlias;

import java.util.Map;

public record PredictionPayloadDto(
        @JsonAlias("as_of_date") String asOfDate,
        @JsonAlias("next_trading_day_target") String nextTradingDayTarget,
        @JsonAlias("policy_path") String policyPath,
        boolean deterministic,
        @JsonAlias("target_weights") Map<String, Double> targetWeights,
        @JsonAlias("weights_capped") boolean weightsCapped,
        boolean renormalized,
        ContextDto context,
        @JsonAlias("triggered_by") String triggeredBy,
        @JsonAlias("inference_id") String inferenceId,
        @JsonAlias("inferred_at_utc") String inferredAtUtc
) {}
