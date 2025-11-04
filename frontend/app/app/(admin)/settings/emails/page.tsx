"use client";

import { useEffect, useMemo, useState } from "react";
import { formatDistanceToNow } from "date-fns";
import { saveEmailTemplate } from "@/lib/api";
import type { EmailTemplate } from "@/lib/types";
import { useAdminData } from "@/providers/admin-data-provider";
import { useSupabaseAuth } from "@/providers/supabase-provider";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";

const TEMPLATE_CONFIGS = [
  {
    key: "candidate_assessment_started",
    title: "Assessment in progress",
    description: "Send a heads-up to candidates after they start their project.",
    recommendedSubject: "You're underway on {assessment_title}",
    recommendedBody:
      "Hi {candidate_name}, your repository {candidate_repo_name} is ready. Keep working at {candidate_repo_url} and aim to finish before {complete_deadline}.",
  },
  {
    key: "candidate_submission_received",
    title: "Submission received",
    description: "Confirm that the candidate's work arrived after they submit.",
    recommendedSubject: "Thanks for submitting {assessment_title}",
    recommendedBody:
      "Hi {candidate_name}, we received your submission for {assessment_title}. We'll review your work shortly.",
  },
] as const;

const VARIABLE_TOKENS = [
  "{candidate_name}",
  "{candidate_email}",
  "{assessment_title}",
  "{start_deadline}",
  "{complete_deadline}",
  "{started_at}",
  "{submitted_at}",
  "{candidate_repo_name}",
  "{candidate_repo_url}",
];

type TemplateEditorProps = {
  config: (typeof TEMPLATE_CONFIGS)[number];
  template: EmailTemplate | undefined;
};

function TemplateEditor({ config, template }: TemplateEditorProps) {
  const { dispatch } = useAdminData();
  const { accessToken } = useSupabaseAuth();
  const [subject, setSubject] = useState(template?.subject ?? "");
  const [body, setBody] = useState(template?.body ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    setSubject(template?.subject ?? "");
    setBody(template?.body ?? "");
    setSaved(false);
    setError(null);
  }, [template?.id, template?.subject, template?.body]);

  const hasChanges =
    subject !== (template?.subject ?? "") || body !== (template?.body ?? "");

  const lastUpdatedLabel = template
    ? formatDistanceToNow(new Date(template.updatedAt), { addSuffix: true })
    : "Not saved yet";

  function handleSubjectChange(value: string) {
    setSubject(value);
    setSaved(false);
    setError(null);
  }

  function handleBodyChange(value: string) {
    setBody(value);
    setSaved(false);
    setError(null);
  }

  async function handleSave() {
    if (!accessToken) {
      setError("Sign in to save templates");
      return;
    }

    const trimmedSubject = subject.trim();
    const trimmedBody = body.trim();

    if (!trimmedSubject || !trimmedBody) {
      setError("Subject and body are required");
      return;
    }

    setSaving(true);
    setError(null);
    try {
      const updated = await saveEmailTemplate(
        config.key,
        { subject: trimmedSubject, body: trimmedBody },
        { accessToken },
      );
      dispatch({ type: "upsertEmailTemplate", payload: updated });
      setSaved(true);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to save template";
      setError(message);
    } finally {
      setSaving(false);
    }
  }

  function handleReset() {
    setSubject(template?.subject ?? "");
    setBody(template?.body ?? "");
    setSaved(false);
    setError(null);
  }

  const disableSave = saving || !hasChanges || !subject.trim() || !body.trim();
  const disableReset = saving || !hasChanges;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{config.title}</CardTitle>
        <CardDescription>{config.description}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        <div className="space-y-2">
          <Label htmlFor={`${config.key}-subject`}>Subject</Label>
          <Input
            id={`${config.key}-subject`}
            value={subject}
            onChange={(event) => handleSubjectChange(event.target.value)}
            placeholder={config.recommendedSubject}
            disabled={saving}
          />
        </div>
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <Label htmlFor={`${config.key}-body`}>Body</Label>
            <span className="text-xs text-zinc-500">Last updated {lastUpdatedLabel}</span>
          </div>
          <Textarea
            id={`${config.key}-body`}
            value={body}
            onChange={(event) => handleBodyChange(event.target.value)}
            placeholder={config.recommendedBody}
            className="min-h-[200px]"
            disabled={saving}
          />
        </div>
        <div className="space-y-2">
          <p className="text-sm text-zinc-500">Available tokens:</p>
          <div className="flex flex-wrap gap-2">
            {VARIABLE_TOKENS.map((token) => (
              <code
                key={`${config.key}-${token}`}
                className="rounded-md bg-zinc-100 px-2 py-1 text-xs text-zinc-700"
              >
                {token}
              </code>
            ))}
          </div>
        </div>
        {error ? (
          <p className="text-sm text-red-500">{error}</p>
        ) : saved ? (
          <p className="text-sm text-emerald-600">Template saved.</p>
        ) : null}
        <div className="flex justify-end gap-3">
          <Button
            variant="outline"
            type="button"
            onClick={handleReset}
            disabled={disableReset}
          >
            Reset
          </Button>
          <Button type="button" onClick={handleSave} disabled={disableSave}>
            {saving ? "Saving..." : template ? "Save changes" : "Create template"}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

export default function EmailSettingsPage() {
  const { state } = useAdminData();

  const templateMap = useMemo(() => {
    const map = new Map<string, EmailTemplate>();
    for (const template of state.emailTemplates) {
      if (template.key) {
        map.set(template.key, template);
      }
    }
    return map;
  }, [state.emailTemplates]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Email templates</h1>
        <p className="text-sm text-zinc-500">
          Configure optional candidate notifications. Emails are only sent when a template is saved.
        </p>
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        {TEMPLATE_CONFIGS.map((config) => (
          <TemplateEditor key={config.key} config={config} template={templateMap.get(config.key)} />
        ))}
      </div>
    </div>
  );
}
