package com.dayitw.warroom.gateway.config;

import com.dayitw.warroom.gateway.service.PredictionBroadcaster;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.listener.ChannelTopic;
import org.springframework.data.redis.listener.RedisMessageListenerContainer;
import org.springframework.util.backoff.FixedBackOff;

@Configuration
@ConditionalOnProperty(prefix = "predictions.redis", name = "enabled", havingValue = "true", matchIfMissing = true)
public class RedisConfig {

    @Bean
    public ChannelTopic predictionsTopic(@Value("${predictions.channel:predictions:latest}") String channel) {
        return new ChannelTopic(channel);
    }

    @Bean
    public RedisMessageListenerContainer redisMessageListenerContainer(
            RedisConnectionFactory connectionFactory,
            PredictionBroadcaster broadcaster,
            ChannelTopic predictionsTopic) {
        var container = new RedisMessageListenerContainer();
        container.setConnectionFactory(connectionFactory);
        container.addMessageListener(broadcaster, predictionsTopic);
        container.setRecoveryBackoff(new FixedBackOff(5000L, FixedBackOff.UNLIMITED_ATTEMPTS));
        return container;
    }
}
