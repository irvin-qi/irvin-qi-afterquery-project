# Plan: Inline Diff Viewer for Review Workspace

## Overview
Display GitHub diff guidance directly within the review workspace without navigating to GitHub, allowing reviewers to see file-by-file changes, line-by-line diffs, and code annotations inline.

## Current State
- Review page shows a link to GitHub compare view (`/compare/{seedSha}...main`)
- Diff guidance tab displays: "Launch compare view" with external GitHub link
- No inline diff rendering or file navigation

## Proposed Solution

### 1. Backend: GitHub Diff API Endpoint

**New Endpoint**: `GET /api/candidate-repos/{repo_id}/diff`

**Purpose**: Fetch and return structured diff data from GitHub Compare API

**Implementation**:
- Use GitHub App installation token to authenticate
- Call GitHub API: `GET /repos/{owner}/{repo}/compare/{base}...{head}`
- Parse and structure the response:
  - File list with stats (additions, deletions, changes)
  - Per-file diff content (unified diff format)
  - Commit information
  - Metadata (total changes, files changed)

**Response Schema**:
```python
class DiffResponse(BaseModel):
    files: List[DiffFile]
    total_additions: int
    total_deletions: int
    total_changes: int
    commits: List[DiffCommit]
    base_sha: str
    head_sha: str

class DiffFile(BaseModel):
    filename: str
    status: str  # "added", "removed", "modified", "renamed"
    additions: int
    deletions: int
    changes: int
    patch: Optional[str]  # Unified diff format
    blob_url: str
    
class DiffCommit(BaseModel):
    sha: str
    message: str
    author: str
    date: datetime
```

**Location**: `backend/app/routes/reviews.py` (new file) or add to existing routes

**Error Handling**:
- Handle missing repo
- Handle GitHub API errors
- Handle empty diffs (no changes)
- Cache responses (optional, for performance)

---

### 2. Frontend: Diff Viewer Component

**New Component**: `frontend/components/review/diff-viewer.tsx`

**Features**:
- File tree/list sidebar for navigation
- File-by-file diff display
- Syntax highlighting for code
- Line-by-line diff rendering (additions/deletions)
- Collapsible file sections
- Loading states
- Error states
- "View on GitHub" fallback button

**UI Layout**:
```
┌─────────────────────────────────────────────────────┐
│ Diff Viewer                              [View on GH]│
├──────────────┬──────────────────────────────────────┤
│ File List    │ Diff Content                         │
│              │                                      │
│ 📁 src/      │ ┌──────────────────────────────────┐ │
│   📄 app.ts  │ │ + added line                     │ │
│   📄 api.ts  │ │ - removed line                   │ │
│              │ │   unchanged line                 │ │
│ 📁 tests/    │ │ + another addition               │ │
│   📄 test.ts │ │                                  │ │
│              │ └──────────────────────────────────┘ │
│              │                                      │
│              │ Stats: +50 -20 = 30 changes         │
└──────────────┴──────────────────────────────────────┘
```

**Dependencies**:
- Consider using a diff library:
  - `react-diff-view` (recommended)
  - `diff2html` 
  - `react-diff-viewer-continuous`
- Or build custom with syntax highlighting:
  - `react-syntax-highlighter` for code highlighting
  - Custom diff parsing

**Component Props**:
```typescript
type DiffViewerProps = {
  repoId: string;
  seedSha: string;
  headBranch?: string; // defaults to "main"
  onError?: (error: Error) => void;
};
```

---

### 3. Frontend: API Integration

**New API Function**: `frontend/lib/api.ts`

```typescript
export async function fetchRepoDiff(
  repoId: string,
  options: ApiRequestOptions = {}
): Promise<DiffResponse>
```

**Error Handling**:
- Network errors
- 404 (repo not found)
- 502 (GitHub API error)
- Empty diff handling

---

### 4. Update Review Page

**File**: `frontend/app/app/(admin)/review/[invitationId]/page.tsx`

**Changes**:
- Replace current "Diff guidance" tab content
- Import and use `DiffViewer` component
- Pass `repo.id`, `repo.seedShaPinned`, and `"main"` as props
- Keep "View on GitHub" button as fallback
- Add loading and error states

**Tab Content Structure**:
```tsx
<TabsContent value="diff">
  <Card>
    <CardHeader>
      <CardTitle>Diff Guidance</CardTitle>
      <CardDescription>
        Changes made by candidate compared to seed repository
      </CardDescription>
    </CardHeader>
    <CardContent>
      {repo ? (
        <DiffViewer 
          repoId={repo.id}
          seedSha={repo.seedShaPinned}
          headBranch="main"
        />
      ) : (
        <p>No repository available</p>
      )}
    </CardContent>
  </Card>
</TabsContent>
```

---

### 5. Implementation Steps

#### Phase 1: Backend API (Priority: High)
1. ✅ Create `backend/app/routes/reviews.py`
2. ✅ Add endpoint `GET /api/candidate-repos/{repo_id}/diff`
3. ✅ Implement GitHub API call using `GitHubAppClient`
4. ✅ Parse and structure diff response
5. ✅ Add error handling
6. ✅ Register route in `backend/app/main.py`

#### Phase 2: Frontend Component (Priority: High)
1. ✅ Install diff viewer library (or decide on custom solution)
2. ✅ Create `frontend/components/review/diff-viewer.tsx`
3. ✅ Implement file list sidebar
4. ✅ Implement diff rendering
5. ✅ Add syntax highlighting
6. ✅ Add loading/error states
7. ✅ Add "View on GitHub" button

#### Phase 3: Integration (Priority: Medium)
1. ✅ Add API function in `frontend/lib/api.ts`
2. ✅ Update review page to use new component
3. ✅ Test with real repository diffs
4. ✅ Handle edge cases (empty diff, large files, etc.)

#### Phase 4: Enhancements (Priority: Low)
1. ⬜ Add file filtering/search
2. ⬜ Add collapse/expand all
3. ⬜ Add diff stats summary
4. ⬜ Add copy file path/line number
5. ⬜ Add permalink to specific files
6. ⬜ Cache diff responses
7. ⬜ Add diff pagination for large changesets

---

### 6. Technical Considerations

**Performance**:
- Large diffs may be slow to render
- Consider pagination or virtual scrolling
- Lazy load file contents
- Cache API responses

**Security**:
- Ensure proper authentication/authorization
- Validate repo belongs to invitation/org
- Rate limit GitHub API calls
- Handle sensitive file paths

**User Experience**:
- Show loading spinner while fetching
- Handle empty states gracefully
- Provide clear error messages
- Always show "View on GitHub" as fallback
- Remember user's file selection/scroll position

**GitHub API Limits**:
- GitHub App installations have rate limits
- Consider caching diff responses
- Handle rate limit errors gracefully

---

### 7. Alternative Approach: GitHub Compare Embed

**Simpler Option**: Use GitHub's native compare view in an iframe

**Pros**:
- No backend API needed
- Native GitHub UI
- Always up-to-date with GitHub features

**Cons**:
- Requires navigating to GitHub (external)
- Less customizable
- Potential CORS/embedding issues
- Doesn't meet requirement of staying in-app

**Decision**: Not recommended for this requirement

---

### 8. Libraries to Consider

**React Diff View**:
- `react-diff-view` - Full-featured, maintained
- Supports unified diff format
- Syntax highlighting included
- File navigation built-in

**Custom Solution**:
- `react-syntax-highlighter` - Syntax highlighting
- `diff` - Parse unified diffs
- Custom components for file tree and diff display

**Recommendation**: Start with `react-diff-view` for faster implementation, can customize later if needed.

---

### 9. Testing Strategy

**Backend**:
- Test with real GitHub repositories
- Test with empty diffs
- Test with large diffs
- Test error cases (missing repo, API failures)

**Frontend**:
- Test with various diff sizes
- Test file navigation
- Test syntax highlighting
- Test error states
- Test loading states

---

### 10. Success Criteria

- ✅ Diff displays inline without leaving app
- ✅ Files can be navigated easily
- ✅ Code is syntax-highlighted
- ✅ Additions/deletions are clearly visible
- ✅ Performance is acceptable for typical diffs (< 100 files)
- ✅ Fallback to GitHub is available
- ✅ Works with existing review workflow

---

## Next Steps

1. Review and approve this plan
2. Start with Phase 1 (Backend API)
3. Iterate on Phase 2 (Frontend Component)
4. Integrate and test (Phase 3)
5. Add enhancements as needed (Phase 4)



