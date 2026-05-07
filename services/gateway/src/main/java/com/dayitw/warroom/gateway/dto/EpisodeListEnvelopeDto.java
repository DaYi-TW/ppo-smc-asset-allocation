package com.dayitw.warroom.gateway.dto;

import com.fasterxml.jackson.annotation.JsonInclude;

import java.util.List;

/**
 * GET /api/v1/episodes envelope (feature 009 / 006 pass-through).
 */
@JsonInclude(JsonInclude.Include.NON_ABSENT)
public record EpisodeListEnvelopeDto(
        List<EpisodeSummaryDto> items,
        ListMetaDto meta
) {

    public record ListMetaDto(int count, String generatedAt) {
    }
}
