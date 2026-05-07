package com.dayitw.warroom.gateway.dto;

import com.fasterxml.jackson.annotation.JsonInclude;

/**
 * Pass-through DTO mirroring 005 inference_service EpisodeSummary schema (feature 009).
 * Field names align with viewmodels/episode.ts EpisodeSummaryViewModel (camelCase).
 */
@JsonInclude(JsonInclude.Include.NON_ABSENT)
public record EpisodeSummaryDto(
        String id,
        String policyId,
        String startDate,
        String endDate,
        int nSteps,
        double initialNav,
        double finalNav,
        double cumulativeReturnPct,
        double annualizedReturnPct,
        double maxDrawdownPct,
        double sharpeRatio,
        double sortinoRatio,
        boolean includeSmc
) {
}
