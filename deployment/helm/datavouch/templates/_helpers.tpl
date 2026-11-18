{{- define "datavouch.name" -}}
{{- printf "%s-datavouch" .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- define "datavouch.labels" -}}
app.kubernetes.io/name: datavouch
app.kubernetes.io/instance: {{ .Release.Name | quote }}
{{- end -}}
{{- define "datavouch.image" -}}
{{- if .Values.image.digest -}}
{{ .Values.image.repository }}@{{ .Values.image.digest }}
{{- else -}}
{{ .Values.image.repository }}:{{ .Values.image.tag }}
{{- end -}}
{{- end -}}
{{- define "datavouch.serviceAccount" -}}
{{- if .Values.serviceAccount.name -}}
{{ .Values.serviceAccount.name }}
{{- else if .Values.serviceAccount.create -}}
{{ include "datavouch.name" . }}
{{- else -}}
default
{{- end -}}
{{- end -}}
