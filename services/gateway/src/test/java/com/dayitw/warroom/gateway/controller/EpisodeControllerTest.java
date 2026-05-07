package com.dayitw.warroom.gateway.controller;

import com.dayitw.warroom.gateway.dto.EpisodeListEnvelopeDto;
import com.dayitw.warroom.gateway.dto.EpisodeSummaryDto;
import com.dayitw.warroom.gateway.exception.InferenceServiceException;
import com.dayitw.warroom.gateway.exception.PredictionNotReadyException;
import com.dayitw.warroom.gateway.service.EpisodeClient;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.test.web.servlet.MockMvc;

import java.util.List;

import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(EpisodeController.class)
class EpisodeControllerTest {

    @Autowired MockMvc mockMvc;
    @MockBean EpisodeClient episodeClient;

    @Test
    void list_returnsPassThroughEnvelope() throws Exception {
        var summary = new EpisodeSummaryDto(
                "test-run", "test-run",
                "2025-01-02", "2026-04-28",
                329, 1.0, 1.7291, 72.91, 52.11,
                15.72, 1.72, 2.30, true);
        var envelope = new EpisodeListEnvelopeDto(
                List.of(summary),
                new EpisodeListEnvelopeDto.ListMetaDto(1, "2026-05-07T00:00:00Z"));
        when(episodeClient.listEpisodes()).thenReturn(envelope);

        mockMvc.perform(get("/api/v1/episodes"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items.length()").value(1))
                .andExpect(jsonPath("$.items[0].id").value("test-run"))
                .andExpect(jsonPath("$.items[0].nSteps").value(329))
                .andExpect(jsonPath("$.meta.count").value(1));
    }

    @Test
    void detail_returnsRawJsonNode() throws Exception {
        ObjectMapper mapper = new ObjectMapper();
        JsonNode body = mapper.readTree("""
                {"data":{"summary":{"id":"test-run","nSteps":3},"trajectoryInline":[]},
                 "meta":{"generatedAt":"2026-05-07T00:00:00Z"}}""");
        when(episodeClient.getEpisodeDetail("test-run")).thenReturn(body);

        mockMvc.perform(get("/api/v1/episodes/test-run"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.summary.id").value("test-run"))
                .andExpect(jsonPath("$.meta.generatedAt").value("2026-05-07T00:00:00Z"));
    }

    @Test
    void detail_404_mapsToPredictionNotReady() throws Exception {
        when(episodeClient.getEpisodeDetail("missing"))
                .thenThrow(new PredictionNotReadyException("episode not found"));
        mockMvc.perform(get("/api/v1/episodes/missing"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.error").value("PredictionNotReady"));
    }

    @Test
    void list_503_when005Unreachable() throws Exception {
        when(episodeClient.listEpisodes())
                .thenThrow(new InferenceServiceException("upstream down", new RuntimeException()));
        mockMvc.perform(get("/api/v1/episodes"))
                .andExpect(status().isServiceUnavailable())
                .andExpect(jsonPath("$.error").value("InferenceServiceUnavailable"));
    }
}
