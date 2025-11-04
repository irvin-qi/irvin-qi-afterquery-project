"use client";

import {
  ReactNode,
  createContext,
  useContext,
  useEffect,
  useMemo,
  useReducer,
  useState,
  useRef,
} from "react";
import { fetchAdminOverview } from "@/lib/api";
import type {
  Assessment,
  CandidateRepo,
  EmailTemplate,
  Invitation,
  ReviewComment,
  Seed,
  AdminUser,
  OrgProfile,
  AdminMembership,
  GitHubInstallation,
} from "@/lib/types";
import { useSupabaseAuth } from "./supabase-provider";

type AdminDataState = {
  seeds: Seed[];
  assessments: Assessment[];
  invitations: Invitation[];
  candidateRepos: CandidateRepo[];
  reviewComments: ReviewComment[];
  emailTemplates: EmailTemplate[];
  githubInstallation: GitHubInstallation | null;
};

type AdminDataAction =
  | { type: "initialize"; payload: AdminDataState }
  | { type: "createSeed"; payload: Seed }
  | { type: "createAssessment"; payload: Assessment }
  | { type: "updateAssessment"; payload: Assessment }
  | { type: "deleteAssessment"; payload: { assessmentId: string } }
  | { type: "createInvitation"; payload: Invitation }
  | {
      type: "updateInvitationStatus";
      payload: { invitationId: string; status: Invitation["status"]; submittedAt?: string };
    }
  | { type: "updateInvitation"; payload: Invitation }
  | { type: "deleteInvitation"; payload: { invitationId: string } }
  | { type: "upsertEmailTemplate"; payload: EmailTemplate }
  | { type: "setGitHubInstallation"; payload: GitHubInstallation | null };

type WorkspaceStatus = "loading" | "needs_org" | "pending_approval" | "ready";

const AdminDataContext = createContext<
  | ({
      state: AdminDataState;
      dispatch: React.Dispatch<AdminDataAction>;
      currentAdmin: AdminUser | null;
      org: OrgProfile | null;
      membership: AdminMembership | null;
      workspaceStatus: WorkspaceStatus;
      loading: boolean;
      githubInstallation: GitHubInstallation | null;
      refreshAdminData: () => void;
    })
  | undefined
>(undefined);

function createEmptyState(): AdminDataState {
  return {
    seeds: [],
    assessments: [],
    invitations: [],
    candidateRepos: [],
    reviewComments: [],
    emailTemplates: [],
    githubInstallation: null,
  };
}

function reducer(state: AdminDataState, action: AdminDataAction): AdminDataState {
  switch (action.type) {
    case "initialize":
      return action.payload;
    case "createSeed":
      return { ...state, seeds: [action.payload, ...state.seeds] };
    case "createAssessment":
      return { ...state, assessments: [action.payload, ...state.assessments] };
    case "updateAssessment":
      return {
        ...state,
        assessments: state.assessments.map((assessment) =>
          assessment.id === action.payload.id ? action.payload : assessment,
        ),
      };
    case "deleteAssessment":
      return {
        ...state,
        assessments: state.assessments.filter(
          (assessment) => assessment.id !== action.payload.assessmentId,
        ),
        // Also remove all invitations for this assessment
        invitations: state.invitations.filter(
          (invitation) => invitation.assessmentId !== action.payload.assessmentId,
        ),
      };
    case "createInvitation":
      return { ...state, invitations: [action.payload, ...state.invitations] };
    case "updateInvitationStatus":
      return {
        ...state,
        invitations: state.invitations.map((invitation) =>
          invitation.id === action.payload.invitationId
            ? {
                ...invitation,
                status: action.payload.status,
                submittedAt: action.payload.submittedAt ?? invitation.submittedAt,
              }
            : invitation,
        ),
      };
    case "updateInvitation":
      return {
        ...state,
        invitations: state.invitations.map((invitation) =>
          invitation.id === action.payload.id ? action.payload : invitation,
        ),
      };
    case "deleteInvitation":
      return {
        ...state,
        invitations: state.invitations.filter(
          (invitation) => invitation.id !== action.payload.invitationId,
        ),
      };
    case "upsertEmailTemplate": {
      const filtered = state.emailTemplates.filter((template) => {
        if (template.id === action.payload.id) {
          return false;
        }
        if (action.payload.key && template.key === action.payload.key) {
          return false;
        }
        return true;
      });
      return {
        ...state,
        emailTemplates: [action.payload, ...filtered],
      };
    }
    case "setGitHubInstallation":
      return { ...state, githubInstallation: action.payload };
    default:
      return state;
  }
}

export function AdminDataProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, undefined, createEmptyState);

  const [currentAdmin, setCurrentAdmin] = useState<AdminUser | null>(null);
  const [org, setOrg] = useState<OrgProfile | null>(null);
  const [membership, setMembership] = useState<AdminMembership | null>(null);
  const [workspaceStatus, setWorkspaceStatus] = useState<WorkspaceStatus>("loading");
  const [loadingState, setLoadingState] = useState<boolean>(true);
  const [refreshTrigger, setRefreshTrigger] = useState(0);
  const hasInitializedRef = useRef(false);

  const { accessToken, loading: authLoading, user: supabaseUser, isConfigured } = useSupabaseAuth();

  const supabaseAdmin = useMemo<AdminUser | null>(() => {
    if (!supabaseUser) {
      return null;
    }
    const metadata = supabaseUser.user_metadata || {};
    const derivedName =
      (typeof metadata.full_name === "string" && metadata.full_name.trim()) ||
      (typeof metadata.name === "string" && metadata.name.trim()) ||
      supabaseUser.email ||
      supabaseUser.id;
    return {
      id: supabaseUser.id,
      email: supabaseUser.email ?? null,
      name: derivedName,
      role: supabaseUser.role ?? null,
    };
  }, [supabaseUser]);

  useEffect(() => {
    if (authLoading) {
      return;
    }

    if (!isConfigured) {
      dispatch({ type: "initialize", payload: createEmptyState() });
      setCurrentAdmin(supabaseAdmin);
      setOrg(null);
      setMembership(null);
      setWorkspaceStatus("loading");
      setLoadingState(false);
      hasInitializedRef.current = false;
      return;
    }

    if (!accessToken) {
      dispatch({ type: "initialize", payload: createEmptyState() });
      setCurrentAdmin(supabaseAdmin);
      setOrg(null);
      setMembership(null);
      setWorkspaceStatus("loading");
      setLoadingState(false);
      hasInitializedRef.current = false;
      return;
    }

    let active = true;
    const controller = new AbortController();
    if (!hasInitializedRef.current) {
      setLoadingState(true);
    }

    fetchAdminOverview<
      Assessment,
      Invitation,
      Seed,
      CandidateRepo,
      ReviewComment,
      EmailTemplate,
      AdminUser,
      OrgProfile,
      AdminMembership
    >({ accessToken, signal: controller.signal })
      .then((data) => {
        if (!active) return;
        dispatch({
          type: "initialize",
          payload: {
            seeds: data.seeds ?? [],
            assessments: data.assessments ?? [],
            invitations: data.invitations ?? [],
            candidateRepos: data.candidateRepos ?? [],
            reviewComments: data.reviewComments ?? [],
            emailTemplates: data.emailTemplates ?? [],
            githubInstallation: data.githubInstallation ?? null,
          },
        });
        setCurrentAdmin(data.currentAdmin ?? supabaseAdmin ?? null);
        setOrg(data.org ?? null);
        setMembership(data.membership ?? null);
        const status: WorkspaceStatus = !data.org
          ? "needs_org"
          : data.membership && !data.membership.isApproved
          ? "pending_approval"
          : "ready";
        setWorkspaceStatus(status);
        setLoadingState(false);
        hasInitializedRef.current = true;
      })
      .catch((error) => {
        if (!active) return;
        console.error("Failed to load admin overview", error);
        if (!hasInitializedRef.current) {
          dispatch({ type: "initialize", payload: createEmptyState() });
          setCurrentAdmin(supabaseAdmin ?? null);
          setOrg(null);
          setMembership(null);
          setWorkspaceStatus("needs_org");
          setLoadingState(false);
        }
      });

    return () => {
      active = false;
      controller.abort();
    };
  }, [accessToken, authLoading, supabaseAdmin, isConfigured, refreshTrigger]);

  // Expose a refresh function that can be called externally
  const refreshAdminData = useMemo(() => {
    return () => {
      if (!accessToken || authLoading || !isConfigured) {
        return;
      }
      // Force a refresh by incrementing the trigger counter
      setRefreshTrigger((prev) => prev + 1);
    };
  }, [accessToken, authLoading, isConfigured]);

  const value = useMemo(
    () => ({
      state,
      dispatch,
      currentAdmin,
      org,
      membership,
      workspaceStatus,
      loading: loadingState,
      githubInstallation: state.githubInstallation,
      refreshAdminData,
    }),
    [state, currentAdmin, org, membership, workspaceStatus, loadingState, refreshAdminData],
  );

  return <AdminDataContext.Provider value={value}>{children}</AdminDataContext.Provider>;
}

export function useAdminData() {
  const ctx = useContext(AdminDataContext);
  if (!ctx) {
    throw new Error("useAdminData must be used within AdminDataProvider");
  }
  return ctx;
}
