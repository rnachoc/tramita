package dev.tramita.core.events;

import com.fasterxml.jackson.databind.ObjectMapper;
import dev.tramita.core.audit.AuditEventRepository;
import java.time.Clock;
import java.time.Duration;
import org.apache.kafka.clients.admin.NewTopic;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.kafka.config.TopicBuilder;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.scheduling.annotation.EnableScheduling;

/**
 * Claim events on Kafka, on only when {@code tramita.events.enabled=true}: the core must keep
 * working, and its tests must run, without a broker. The audit trail keeps every event until the
 * relay catches up.
 */
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(name = "tramita.events.enabled", havingValue = "true")
@EnableScheduling
public class EventsConfiguration {

  @Bean
  EventRelay.EventsProperties eventsProperties(
      @Value("${tramita.events.topic}") String topic,
      @Value("${tramita.events.batch-size:200}") int batchSize,
      @Value("${tramita.events.gap-grace:30s}") Duration gapGrace,
      @Value("${tramita.events.send-timeout:10s}") Duration sendTimeout) {
    return new EventRelay.EventsProperties(topic, batchSize, gapGrace, sendTimeout);
  }

  /** Created at start-up: the broker does not create topics on its own. */
  @Bean
  NewTopic claimEventsTopic(
      EventRelay.EventsProperties properties,
      @Value("${tramita.events.partitions:3}") int partitions) {
    return TopicBuilder.name(properties.topic()).partitions(partitions).replicas(1).build();
  }

  @Bean
  EventRelay eventRelay(
      AuditEventRepository events,
      JdbcTemplate jdbc,
      KafkaTemplate<String, String> kafka,
      ObjectMapper json,
      Clock clock,
      EventRelay.EventsProperties properties) {
    return new EventRelay(events, jdbc, kafka, json, clock, properties);
  }
}
