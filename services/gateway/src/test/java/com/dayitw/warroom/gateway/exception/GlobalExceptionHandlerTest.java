package com.dayitw.warroom.gateway.exception;

import com.dayitw.warroom.gateway.controller.InferenceController;
import com.dayitw.warroom.gateway.service.InferenceClient;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(InferenceController.class)
class GlobalExceptionHandlerTest {

    @Autowired MockMvc mockMvc;
    @MockBean InferenceClient inferenceClient;

    @Test
    void inferenceServiceException_returns503WithErrorDto() throws Exception {
        when(inferenceClient.runInference()).thenThrow(new InferenceServiceException("boom"));
        mockMvc.perform(post("/api/v1/inference/run"))
                .andExpect(status().isServiceUnavailable())
                .andExpect(jsonPath("$.error").value("InferenceServiceUnavailable"))
                .andExpect(jsonPath("$.message").exists())
                .andExpect(jsonPath("$.requestId").exists());
    }

    @Test
    void runtimeException_returns500_doesNotLeakStack() throws Exception {
        when(inferenceClient.runInference()).thenThrow(new RuntimeException("internal kaboom secret_token=abc"));
        mockMvc.perform(post("/api/v1/inference/run"))
                .andExpect(status().isInternalServerError())
                .andExpect(jsonPath("$.error").value("InternalServerError"))
                .andExpect(jsonPath("$.message").value("Unexpected internal error"))
                .andExpect(jsonPath("$.requestId").exists());
    }
}
