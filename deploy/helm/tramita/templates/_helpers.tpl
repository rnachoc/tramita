{{- define "tramita.fullname" -}}
{{- printf "%s" .Release.Name | trunc 40 | trimSuffix "-" -}}
{{- end -}}

{{- define "tramita.labels" -}}
app.kubernetes.io/part-of: tramita
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/instance: {{ .Release.Name }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version }}
{{- end -}}

{{- define "tramita.selector" -}}
app.kubernetes.io/instance: {{ .root.Release.Name }}
app.kubernetes.io/component: {{ .component }}
{{- end -}}

{{/* A name for one component: <release>-<component>. */}}
{{- define "tramita.name" -}}
{{- printf "%s-%s" (include "tramita.fullname" .root) .component -}}
{{- end -}}

{{/* Pod security for the application images (uid 10001, read-only root, no capabilities). */}}
{{- define "tramita.podSecurity" -}}
securityContext:
  runAsNonRoot: true
  runAsUser: {{ .uid | default 10001 }}
  runAsGroup: {{ .uid | default 10001 }}
  fsGroup: {{ .uid | default 10001 }}
  seccompProfile:
    type: RuntimeDefault
{{- end -}}

{{- define "tramita.containerSecurity" -}}
securityContext:
  allowPrivilegeEscalation: false
  readOnlyRootFilesystem: true
  capabilities:
    drop: ["ALL"]
{{- end -}}

{{/*
Secrets are generated on first install and read back on upgrade, so they never live in values
or in the repository and do not change under a running system.
*/}}
{{- define "tramita.secretValue" -}}
{{- $secret := lookup "v1" "Secret" .root.Release.Namespace (printf "%s-secrets" (include "tramita.fullname" .root)) -}}
{{- if and $secret (hasKey $secret.data .key) -}}
{{- index $secret.data .key | b64dec -}}
{{- else -}}
{{- randAlphaNum 32 -}}
{{- end -}}
{{- end -}}

{{/* Environment shared by the agent service's processes. */}}
{{- define "tramita.agentsEnv" -}}
- name: TRAMITA_CORE_URL
  value: http://{{ include "tramita.name" (dict "root" . "component" "core") }}:8080
- name: TRAMITA_API_KEYS
  valueFrom: {secretKeyRef: {name: {{ include "tramita.fullname" . }}-secrets, key: api-keys}}
- name: POSTGRES_HOST
  value: {{ include "tramita.name" (dict "root" . "component" "postgres") }}
- name: POSTGRES_PASSWORD
  valueFrom: {secretKeyRef: {name: {{ include "tramita.fullname" . }}-secrets, key: postgres-password}}
- name: OPENSEARCH_URL
  value: http://{{ include "tramita.name" (dict "root" . "component" "opensearch") }}:9200
- name: S3_ENDPOINT
  value: http://{{ include "tramita.name" (dict "root" . "component" "object-store") }}:9000
- name: S3_SECRET_KEY
  valueFrom: {secretKeyRef: {name: {{ include "tramita.fullname" . }}-secrets, key: s3-secret}}
- name: KAFKA_BOOTSTRAP_SERVERS
  value: {{ include "tramita.name" (dict "root" . "component" "kafka") }}:9092
- name: TEMPORAL_ADDRESS
  value: {{ include "tramita.name" (dict "root" . "component" "temporal") }}:7233
- name: TRAMITA_EMBEDDING_MODEL
  value: {{ .Values.agents.embeddingModel | quote }}
- name: TRAMITA_RERANKER_MODEL
  value: {{ .Values.agents.rerankerModel | quote }}
- name: TRAMITA_MODELS_DIR
  value: /models
{{- if .Values.agents.anthropicSecret }}
- name: ANTHROPIC_API_KEY
  valueFrom: {secretKeyRef: {name: {{ .Values.agents.anthropicSecret }}, key: ANTHROPIC_API_KEY}}
{{- end }}
{{- if .Values.otlpEndpoint }}
- name: OTEL_EXPORTER_OTLP_ENDPOINT
  value: {{ .Values.otlpEndpoint | quote }}
{{- end }}
{{- end -}}
