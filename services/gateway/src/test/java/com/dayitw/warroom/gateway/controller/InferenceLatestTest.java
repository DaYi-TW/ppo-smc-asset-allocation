package com.dayitw.warroom.gateway.controller;

import com.dayitw.warroom.gateway.dto.ContextDto;
import com.dayitw.warroom.gateway.dto.PredictionPayloadDto;
import com.dayitw.warroom.gateway.exception.PredictionNotReadyException;
import com.dayitw.warroom.gateway.service.InferenceClient;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.test.web.servlet.MockMvc;

import java.util.Map;

import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(InferenceController.class)
class InferenceLatestTest {

    @Autowired MockMvc mockMvc;
    @MockBean InferenceClient inferenceClient;

    @Test
    void getLatest_returnsTransparentPayload() throws Exception {
        var payload = new PredictionPayloadDto(
                "2026-04-28", "next session", "/p.zip", true,
                Map.of("CASH", 1.0), false, false,
                new ContextDto("data/raw", true, 100, 1.0),
                "scheduled", "550e8400-e29b-41d4-a716-446655440000",
                "2026-05-06T00:00:00Z");
        when(inferenceClient.getLatest()).thenReturn(payload);

        mockMvc.perform(get("/api/v1/inference/latest"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.asOfDate").value("2026-04-28"))
                .andExpect(jsonPath("$.triggeredBy").value("scheduled"));
    }

    @Test
    void getLatest_404_returnsPredictionNotReady() throws Exception {
        when(inferenceClient.getLatest()).thenThrow(new PredictionNotReadyException("no prediction"));
        mockMvc.perform(get("/api/v1/inference/latest"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.error").value("PredictionNotReady"));
    }
}
