package com.dayitw.warroom.gateway.controller;

import com.dayitw.warroom.gateway.dto.HealthDto;
import com.dayitw.warroom.gateway.exception.InferenceServiceException;
import com.dayitw.warroom.gateway.service.InferenceClient;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(InferenceController.class)
class InferenceHealthzTest {

    @Autowired MockMvc mockMvc;
    @MockBean InferenceClient inferenceClient;

    @Test
    void getHealthz_passThrough_ok() throws Exception {
        when(inferenceClient.getHealthz()).thenReturn(new HealthDto("ok", 42, true, true, null, null));
        mockMvc.perform(get("/api/v1/inference/healthz"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("ok"))
                .andExpect(jsonPath("$.policyLoaded").value(true));
    }

    @Test
    void getHealthz_serviceDown_returns503() throws Exception {
        when(inferenceClient.getHealthz()).thenThrow(new InferenceServiceException("down"));
        mockMvc.perform(get("/api/v1/inference/healthz"))
                .andExpect(status().isServiceUnavailable())
                .andExpect(jsonPath("$.error").value("InferenceServiceUnavailable"));
    }
}
