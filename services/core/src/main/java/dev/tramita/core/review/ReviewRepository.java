package dev.tramita.core.review;

import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ReviewRepository extends JpaRepository<Review, UUID> {

  Optional<Review> findByIdempotencyKey(String idempotencyKey);

  List<Review> findByClaimClaimIdOrderByCreatedAtAsc(String claimId);

  List<Review> findByActionOrderByCreatedAtAsc(ReviewAction action);
}
