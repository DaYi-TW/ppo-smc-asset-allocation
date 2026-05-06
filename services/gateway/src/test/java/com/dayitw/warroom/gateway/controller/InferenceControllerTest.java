package com.dayitw.warroom.gateway.controller;

import com.dayitw.warroom.gateway.exception.InferenceBusyException;
import com.dayitw.warroom.gateway.exception.InferenceServiceException;
import com.dayitw.warroom.gateway.exception.InferenceTimeoutException;
import com.dayitw.warroom.gateway.service.InferenceClient;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import java.util.LinkedHashMap;
import java.util.Map;

import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(InferenceController.class)
class InferenceControllerTest {

    @Autowired MockMvc mockMvc;
    @Autowired ObjectMapper objectMapper;
    @MockBean InferenceClient inferenceClient;

    @Test
    void postRun_returnsCamelCaseBodyAndRequestIdHeader() throws Exception {
        Map<String, Double> weights = new LinkedHashMap<>();
        weights.put("NVDA", 0.1);
        weights.put("CASH", 0.9);
        var ctx = new com.dayitw.warroom.gateway.dto.ContextDto("data/raw", true, 100, 1.0);
        var payload = new com.dayitw.warroom.gateway.dto.PredictionPayloadDto(
                "2026-04-28",
                "first session after 2026-04-28 (apply at next open)",
                "/app/runs/x/final_policy.zip",
                true,
                weights,
                false,
                false,
                ctx,
                "manual",
                "550e8400-e29b-41d4-a716-446655440000",
                "2026-05-06T00:00:00Z");
        when(inferenceClient.runInference()).thenReturn(payload);

        mockMvc.perform(post("/api/v1/inference/run").contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(header().exists("X-Request-Id"))
                .andExpect(jsonPath("$.asOfDate").value("2026-04-28"))
                .andExpect(jsonPath("$.targetWeights.NVDA").value(0.1))
                .andExpect(jsonPath("$.context.currentNavAtAsOf").value(1.0));
    }

    @Test
    void postRun_busy_returns409() throws Exception {
        when(inferenceClient.runInference()).thenThrow(new InferenceBusyException("busy"));
        mockMvc.perform(post("/api/v1/inference/run"))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.error").value("InferenceBusy"))
                .andExpect(jsonPath("$.requestId").exists());
    }

    @Test
    void postRun_timeout_returns504() throws Exception {
        when(inferenceClient.runInference()).thenThrow(new InferenceTimeoutException("timed out"));
        mockMvc.perform(post("/api/v1/inference/run"))
                .andExpect(status().isGatewayTimeout())
                .andExpect(jsonPath("$.error").value("InferenceTimeout"));
    }

    @Test
    void postRun_serviceDown_returns503() throws Exception {
        when(inferenceClient.runInference()).thenThrow(new InferenceServiceException("connection refused"));
        mockMvc.perform(post("/api/v1/inference/run"))
                .andExpect(status().isServiceUnavailable())
                .andExpect(jsonPath("$.error").value("InferenceServiceUnavailable"));
    }
}
