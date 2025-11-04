"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { Markdown } from "@/components/ui/markdown";
import {
  getLLMAnalysis,
  generateLLMAnalysis,
  getLLMConversationHistory,
  askLLMQuestion,
  type ReviewLLMAnalysis,
  type LLMConversationMessage,
} from "@/lib/api";

interface LLMAnalysisTabProps {
  invitationId: string;
  accessToken?: string;
  rubricText?: string | null;
}

export function LLMAnalysisTab({ invitationId, accessToken, rubricText }: LLMAnalysisTabProps) {
  const [analysis, setAnalysis] = useState<ReviewLLMAnalysis | null>(null);
  const [loadingAnalysis, setLoadingAnalysis] = useState(false);
  const [generatingAnalysis, setGeneratingAnalysis] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [conversation, setConversation] = useState<LLMConversationMessage[]>([]);
  const [loadingConversation, setLoadingConversation] = useState(false);
  const [question, setQuestion] = useState("");
  const [askingQuestion, setAskingQuestion] = useState(false);

  // Load existing analysis
  useEffect(() => {
    async function loadAnalysis() {
      setLoadingAnalysis(true);
      setError(null);
      try {
        const existing = await getLLMAnalysis(invitationId, { accessToken });
        setAnalysis(existing);
      } catch (err: any) {
        // 404 is expected when no analysis exists yet - don't log or show error
        if (err?.status === 404) {
          setAnalysis(null);
          return;
        }
        // Only log and show errors for actual failures
        console.error("Failed to load LLM analysis:", err);
        setError(err?.message || "Failed to load analysis");
      } finally {
        setLoadingAnalysis(false);
      }
    }

    loadAnalysis();
  }, [invitationId, accessToken]);

  // Load conversation history
  useEffect(() => {
    async function loadConversation() {
      setLoadingConversation(true);
      try {
        const history = await getLLMConversationHistory(invitationId, { accessToken });
        setConversation(history);
      } catch (err) {
        console.error("Failed to load conversation history:", err);
      } finally {
        setLoadingConversation(false);
      }
    }

    loadConversation();
  }, [invitationId, accessToken]);

  async function handleGenerateAnalysis(regenerate: boolean = false) {
    console.log(`🚀 [Frontend] Starting LLM analysis generation (regenerate: ${regenerate})`);
    console.log(`📝 [Frontend] Invitation ID: ${invitationId}`);
    setGeneratingAnalysis(true);
    setError(null);
    try {
      console.log(`🌐 [Frontend] Calling generateLLMAnalysis API...`);
      const result = await generateLLMAnalysis(invitationId, regenerate, { accessToken });
      console.log(`✅ [Frontend] Analysis generated successfully. Length: ${result?.analysisText?.length || 0} chars`);
      setAnalysis(result);
      // Reload conversation to include any initial analysis context
      console.log(`📥 [Frontend] Reloading conversation history...`);
      const history = await getLLMConversationHistory(invitationId, { accessToken });
      console.log(`✅ [Frontend] Conversation history loaded. Messages: ${history?.length || 0}`);
      setConversation(history);
    } catch (err: any) {
      console.error("❌ [Frontend] Failed to generate analysis:", err);
      console.error("❌ [Frontend] Error details:", {
        status: err?.status,
        message: err?.message,
        detail: err?.detail,
      });
      setError(err?.message || "Failed to generate analysis. Make sure the assessment has a rubric.");
    } finally {
      setGeneratingAnalysis(false);
      console.log(`🏁 [Frontend] Analysis generation process completed`);
    }
  }

  async function handleAskQuestion() {
    if (!question.trim() || askingQuestion) return;

    const questionText = question.trim();
    setQuestion("");
    setAskingQuestion(true);
    setError(null);

    try {
      const response = await askLLMQuestion(invitationId, questionText, { accessToken });
      // Reload full conversation history to get the updated state
      const history = await getLLMConversationHistory(invitationId, { accessToken });
      setConversation(history);
    } catch (err: any) {
      console.error("Failed to ask question:", err);
      setError(err?.message || "Failed to ask question. Make sure the assessment has a rubric.");
      setQuestion(questionText); // Restore question on error
    } finally {
      setAskingQuestion(false);
    }
  }

  return (
    <Tabs defaultValue="analysis" className="w-full">
      <TabsList className="grid w-full grid-cols-2">
        <TabsTrigger value="analysis">Analysis</TabsTrigger>
        <TabsTrigger value="questions">Ask Questions</TabsTrigger>
      </TabsList>

      <TabsContent value="analysis" className="space-y-4">
        <div className="grid gap-6 lg:grid-cols-2">
          {/* Review Rubric - Left Side */}
          <Card>
            <CardHeader>
              <CardTitle>Review Rubric</CardTitle>
              <CardDescription>Guidelines for evaluating this submission.</CardDescription>
            </CardHeader>
            <CardContent>
              {rubricText ? (
                <div className="prose prose-sm max-w-none">
                  <Markdown>{rubricText}</Markdown>
                </div>
              ) : (
                <p className="text-sm text-gray-500">No rubric available for this assessment.</p>
              )}
            </CardContent>
          </Card>

          {/* LLM Code Analysis - Right Side */}
          <Card>
          <CardHeader>
            <CardTitle>LLM Code Analysis</CardTitle>
            <CardDescription>
              AI-powered analysis of how well the code adheres to the assessment rubric.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {error && (
              <div className="rounded-md bg-red-50 p-4 text-sm text-red-800 border border-red-200">
                {error}
              </div>
            )}

            {loadingAnalysis ? (
              <div className="text-center py-8 text-gray-500">Loading analysis...</div>
            ) : analysis ? (
              <div className="space-y-4">
                <div className="prose max-w-none">
                  <Markdown>{analysis.analysisText}</Markdown>
                </div>
                {analysis.modelUsed && (
                  <div className="text-sm text-gray-500 border-t pt-4">
                    Generated using {analysis.modelUsed}
                    {analysis.createdAt && (
                      <> • {new Date(analysis.createdAt).toLocaleString()}</>
                    )}
                  </div>
                )}
                <div className="flex gap-2">
                  <Button
                    onClick={() => handleGenerateAnalysis(true)}
                    disabled={generatingAnalysis}
                    variant="outline"
                  >
                    {generatingAnalysis ? "Regenerating..." : "Regenerate Analysis"}
                  </Button>
                </div>
              </div>
            ) : (
              <div className="text-center py-8 space-y-4">
                <p className="text-gray-500">
                  No analysis generated yet. Click the button below to generate an AI-powered
                  analysis of the code based on the assessment rubric.
                </p>
                <Button
                  onClick={() => handleGenerateAnalysis(false)}
                  disabled={generatingAnalysis}
                >
                  {generatingAnalysis ? "Generating..." : "Generate Analysis"}
                </Button>
              </div>
            )}

            {generatingAnalysis && (
              <div className="text-center py-4 text-gray-500">
                Generating analysis... This may take a minute.
              </div>
            )}
          </CardContent>
        </Card>
      </div>
      </TabsContent>

      <TabsContent value="questions" className="space-y-4">
        <Card>
          <CardHeader>
            <CardTitle>Ask Questions About the Code</CardTitle>
            <CardDescription>
              Ask the AI questions about the codebase. The AI has access to the rubric, file diffs,
              and previous analysis.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {error && (
              <div className="rounded-md bg-red-50 p-4 text-sm text-red-800 border border-red-200">
                {error}
              </div>
            )}

            {/* Conversation History */}
            <div className="space-y-4 max-h-[500px] overflow-y-auto border rounded-lg p-4">
              {loadingConversation ? (
                <div className="text-center py-4 text-gray-500">Loading conversation...</div>
              ) : conversation.length === 0 ? (
                <div className="text-center py-8 text-gray-500">
                  No conversation yet. Ask a question to get started!
                </div>
              ) : (
                conversation.map((message) => (
                  <div
                    key={message.id}
                    className={`flex ${
                      message.messageType === "user" ? "justify-end" : "justify-start"
                    }`}
                  >
                    <div
                      className={`max-w-[80%] rounded-lg p-3 ${
                        message.messageType === "user"
                          ? "bg-blue-100 text-blue-900"
                          : "bg-gray-100 text-gray-900"
                      }`}
                    >
                      <div className="prose prose-sm max-w-none">
                        <Markdown>{message.messageText}</Markdown>
                      </div>
                      {message.modelUsed && (
                        <div className="text-xs text-gray-500 mt-2">
                          {new Date(message.createdAt).toLocaleString()}
                        </div>
                      )}
                    </div>
                  </div>
                ))
              )}
            </div>

            {/* Question Input */}
            <div className="space-y-2">
              <Textarea
                placeholder="Ask a question about the code (e.g., 'How does the error handling work?' or 'What are the main security concerns?')"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                    e.preventDefault();
                    handleAskQuestion();
                  }
                }}
                rows={3}
              />
              <div className="flex justify-between items-center">
                <p className="text-xs text-gray-500">
                  Press Cmd+Enter (Mac) or Ctrl+Enter (Windows) to send
                </p>
                <Button
                  onClick={handleAskQuestion}
                  disabled={!question.trim() || askingQuestion}
                >
                  {askingQuestion ? "Asking..." : "Ask Question"}
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      </TabsContent>
    </Tabs>
  );
}
