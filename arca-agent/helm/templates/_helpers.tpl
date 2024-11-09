{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
*/}}
{{- define "arca-agent.fullname" -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{/*
Generate basic labels
*/}}
{{- define "arca-agent.labels" -}}
app.kubernetes.io/name: "{{ include "arca-agent.fullname" . }}"
app.kubernetes.io/instance: "{{ .Release.Name }}"
app.kubernetes.io/version: "{{ .Chart.AppVersion }}"
app.kubernetes.io/managed-by: "Helm"
{{- end -}}

{{/*
Generate selector labels
*/}}
{{- define "arca-agent.selectorLabels" -}}
app.kubernetes.io/name: {{ include "arca-agent.fullname" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}} 