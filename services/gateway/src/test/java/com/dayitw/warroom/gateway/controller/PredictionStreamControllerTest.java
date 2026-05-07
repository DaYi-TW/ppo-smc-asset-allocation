package com.dayitw.warroom.gateway.controller;

import com.dayitw.warroom.gateway.dto.ContextDto;
import com.dayitw.warroom.gateway.dto.PredictionPayloadDto;
import com.dayitw.warroom.gateway.exception.PredictionNotReadyException;
import com.dayitw.warroom.gateway.service.InferenceClient;
import com.dayitw.warroom.gateway.service.PredictionBroadcaster;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.test.web.servlet.MockMvc;

import java.util.Map;

import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(PredictionStreamController.class)
class PredictionStreamControllerTest {

    @Autowired MockMvc mockMvc;
    @MockBean PredictionBroadcaster broadcaster;
    @MockBean InferenceClient inferenceClient;

    @Test
    void getStream_startsAsync_andRegistersBroadcasterClient() throws Exception {
        when(inferenceClient.getLatest()).thenThrow(new PredictionNotReadyException("none yet"));
        mockMvc.perform(get("/api/v1/predictions/stream"))
                .andExpect(status().isOk())
                .andExpect(request().asyncStarted());
        verify(broadcaster, times(1)).addClient(org.mockito.ArgumentMatchers.any());
    }

    @Test
    void getStream_pushesInitialState_whenLatestAvailable() throws Exception {
        var payload = new PredictionPayloadDto(
                "2026-04-28", "next", "/p.zip", true,
                Map.of("CASH", 1.0), false, false,
                new ContextDto("data/raw", true, 100, 1.0),
                "scheduled", "550e8400-e29b-41d4-a716-446655440000",
                "2026-05-06T00:00:00Z");
        when(inferenceClient.getLatest()).thenReturn(payload);

        mockMvc.perform(get("/api/v1/predictions/stream"))
                .andExpect(request().asyncStarted());
        verify(broadcaster).pushInitialState(org.mockito.ArgumentMatchers.any(),
                org.mockito.ArgumentMatchers.eq(payload));
    }
}
