package com.example.backend_spring.Repository;

import com.example.backend_spring.Entity.DetectionRequestEntity;
import org.springframework.data.jpa.repository.JpaRepository;

public interface DetectionRequestRepository extends JpaRepository<DetectionRequestEntity, Long> {
}