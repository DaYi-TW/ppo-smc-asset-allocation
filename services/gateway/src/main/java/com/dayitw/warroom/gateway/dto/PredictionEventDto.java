package com.dayitw.warroom.gateway.dto;

import com.fasterxml.jackson.annotation.JsonInclude;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record PredictionEventDto(
        String eventType,
        String emittedAtUtc,
        PredictionPayloadDto payload
) {}
