package com.citysense.platform.audit;

import com.citysense.platform.auth.AuthUser;
import java.util.Map;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AuditService {

    public static final String SYSTEM = "system";

    private final AuditLogRepository repo;

    public AuditService(AuditLogRepository repo) {
        this.repo = repo;
    }

    /** Joins the caller's transaction so the audit entry commits or rolls back with the change it describes. */
    @Transactional(propagation = Propagation.MANDATORY)
    public AuditLog record(String actor, String action, String entityType, String entityId, String outcome,
                           Map<String, Object> evidence) {
        return repo.save(new AuditLog(actor, action, entityType, entityId, outcome, evidence));
    }

    @Transactional(propagation = Propagation.MANDATORY)
    public AuditLog record(String action, String entityType, String entityId, String outcome,
                           Map<String, Object> evidence) {
        return record(currentActor(), action, entityType, entityId, outcome, evidence);
    }

    @Transactional(readOnly = true)
    public Page<AuditLog> search(String entityType, String entityId, Pageable pageable) {
        if (entityType != null && entityId != null) {
            return repo.findByEntityTypeAndEntityIdOrderByCreatedAtDesc(entityType, entityId, pageable);
        }
        if (entityType != null) {
            return repo.findByEntityTypeOrderByCreatedAtDesc(entityType, pageable);
        }
        return repo.findAllByOrderByCreatedAtDesc(pageable);
    }

    public static String currentActor() {
        Authentication auth = SecurityContextHolder.getContext().getAuthentication();
        if (auth == null) {
            return SYSTEM;
        }
        return auth.getPrincipal() instanceof AuthUser u ? u.email() : String.valueOf(auth.getPrincipal());
    }
}
