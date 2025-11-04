# Ranking & Scoring Feature Plan

## Overview
Add a comprehensive ranking and scoring system for candidate assessments. Each assessment will have a rubric (markdown text) and weighted features that reviewers can check off when evaluating submissions. Scores are calculated automatically based on which features are checked.

## Requirements Summary
1. **Rubric per Assessment**: Text-based rubric (markdown) that displays in reviews
2. **Feature Management**: Checkbox criteria/features with weights assigned to each assessment
3. **Review Scoring**: Reviewers can check/uncheck features during review
4. **Score Calculation**: Automatic calculation based on checked features × their weights

---

## Database Schema Changes

### 1. Update `assessments` table
Add `rubric_text` column to store the rubric content:
```sql
ALTER TABLE assessments
  ADD COLUMN IF NOT EXISTS rubric_text text;
```

### 2. Create `assessment_features` table
Store the features/criteria for each assessment:
```sql
CREATE TABLE IF NOT EXISTS assessment_features (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  assessment_id uuid REFERENCES assessments(id) ON DELETE CASCADE NOT NULL,
  name text NOT NULL,
  description text,
  weight decimal(10, 2) NOT NULL DEFAULT 1.0,
  display_order integer NOT NULL DEFAULT 0,
  created_at timestamptz DEFAULT now(),
  UNIQUE (assessment_id, name)
);
CREATE INDEX IF NOT EXISTS idx_assessment_features_assessment_id 
  ON assessment_features(assessment_id);
```

**Fields:**
- `id`: Primary key
- `assessment_id`: Foreign key to assessments
- `name`: Feature name (e.g., "Authentication implemented")
- `description`: Optional description
- `weight`: Numeric weight for scoring (e.g., 2.5 for important features, 1.0 for standard)
- `display_order`: For ordering features in UI

### 3. Create `review_feature_scores` table
Track which features were checked for each invitation/review:
```sql
CREATE TABLE IF NOT EXISTS review_feature_scores (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  invitation_id uuid REFERENCES invitations(id) ON DELETE CASCADE NOT NULL,
  feature_id uuid REFERENCES assessment_features(id) ON DELETE CASCADE NOT NULL,
  checked boolean NOT NULL DEFAULT false,
  created_by uuid,
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now(),
  UNIQUE (invitation_id, feature_id)
);
CREATE INDEX IF NOT EXISTS idx_review_feature_scores_invitation_id 
  ON review_feature_scores(invitation_id);
CREATE INDEX IF NOT EXISTS idx_review_feature_scores_feature_id 
  ON review_feature_scores(feature_id);
```

**Fields:**
- `id`: Primary key
- `invitation_id`: Which candidate submission this applies to
- `feature_id`: Which feature was checked/unchecked
- `checked`: Boolean indicating if feature is met
- `created_by`: Reviewer who made the assessment
- `created_at`/`updated_at`: Timestamps

### 4. Optional: Add computed score to `review_feedback`
We could add a `calculated_score` and `max_score` to track totals:
```sql
ALTER TABLE review_feedback
  ADD COLUMN IF NOT EXISTS calculated_score decimal(10, 2),
  ADD COLUMN IF NOT EXISTS max_score decimal(10, 2);
```

**Note**: This is optional - we can calculate on-the-fly, but storing it allows historical tracking if weights change.

---

## Backend Implementation

### Models (`backend/app/models.py`)

Add three new models:

```python
class AssessmentFeature(Base, TimestampMixin):
    __tablename__ = "assessment_features"
    __table_args__ = (
        UniqueConstraint("assessment_id", "name", name="uq_assessment_feature_name"),
        Index("idx_assessment_features_assessment_id", "assessment_id"),
    )
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    assessment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    weight: Mapped[float] = mapped_column(Numeric(10, 2), default=1.0, nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    assessment: Mapped["Assessment"] = relationship(back_populates="features")
    scores: Mapped[list["ReviewFeatureScore"]] = relationship(back_populates="feature")


class ReviewFeatureScore(Base, TimestampMixin):
    __tablename__ = "review_feature_scores"
    __table_args__ = (
        UniqueConstraint("invitation_id", "feature_id", name="uq_review_feature_score"),
        Index("idx_review_feature_scores_invitation_id", "invitation_id"),
        Index("idx_review_feature_scores_feature_id", "feature_id"),
    )
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    invitation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invitations.id", ondelete="CASCADE"), nullable=False
    )
    feature_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assessment_features.id", ondelete="CASCADE"), nullable=False
    )
    checked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    
    invitation: Mapped["Invitation"] = relationship(back_populates="feature_scores")
    feature: Mapped["AssessmentFeature"] = relationship(back_populates="scores")
```

Update `Assessment` model:
```python
# Add to Assessment class
rubric_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
features: Mapped[list["AssessmentFeature"]] = relationship(back_populates="assessment")
```

Update `Invitation` model:
```python
# Add to Invitation class
feature_scores: Mapped[list["ReviewFeatureScore"]] = relationship(back_populates="invitation")
```

Update `ReviewFeedback` model (optional):
```python
# Add to ReviewFeedback class
calculated_score: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
max_score: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
```

### Schemas (`backend/app/schemas.py`)

Add new Pydantic schemas:

```python
class AssessmentFeatureCreate(CamelModel):
    name: str
    description: Optional[str] = None
    weight: float = Field(default=1.0, ge=0.0)
    display_order: int = Field(default=0)


class AssessmentFeatureRead(AssessmentFeatureCreate):
    id: UUID
    assessment_id: UUID
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


class AssessmentFeatureUpdate(CamelModel):
    name: Optional[str] = None
    description: Optional[str] = None
    weight: Optional[float] = Field(None, ge=0.0)
    display_order: Optional[int] = None


class ReviewFeatureScoreCreate(CamelModel):
    feature_id: UUID
    checked: bool


class ReviewFeatureScoreRead(CamelModel):
    id: UUID
    invitation_id: UUID
    feature_id: UUID
    checked: bool
    created_by: Optional[UUID]
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


class ReviewFeatureScoreUpdate(CamelModel):
    checked: bool


class ReviewScoreSummary(CamelModel):
    """Calculated score for an invitation"""
    invitation_id: UUID
    total_score: float
    max_score: float
    percentage: float  # (total_score / max_score) * 100
    features: List[dict]  # List of {feature_id, name, weight, checked, score}


# Update AssessmentCreate to include rubric_text
class AssessmentCreate(BaseModel):
    # ... existing fields ...
    rubric_text: Optional[str] = None


# Update AssessmentRead to include rubric_text
class AssessmentRead(AssessmentCreate):
    # ... existing fields ...
    rubric_text: Optional[str] = None
```

### API Routes

#### 1. Assessment Features CRUD (`backend/app/routes/assessment_features.py`)

New router for managing features:

```python
router = APIRouter(prefix="/api/assessments/{assessment_id}/features", tags=["assessment-features"])

@router.post("", response_model=schemas.AssessmentFeatureRead, status_code=201)
async def create_assessment_feature(
    assessment_id: str,
    payload: schemas.AssessmentFeatureCreate,
    session: AsyncSession = Depends(get_session),
    current_session: SupabaseSession = Depends(require_roles("authenticated", "service_role")),
) -> schemas.AssessmentFeatureRead:
    # Verify assessment exists and user has access
    # Create feature
    # Return created feature


@router.get("", response_model=List[schemas.AssessmentFeatureRead])
async def list_assessment_features(
    assessment_id: str,
    session: AsyncSession = Depends(get_session),
    current_session: SupabaseSession = Depends(require_roles("authenticated", "service_role")),
) -> List[schemas.AssessmentFeatureRead]:
    # List all features for assessment, ordered by display_order


@router.get("/{feature_id}", response_model=schemas.AssessmentFeatureRead)
async def get_assessment_feature(
    assessment_id: str,
    feature_id: str,
    # ... similar to above
) -> schemas.AssessmentFeatureRead:
    # Get single feature


@router.patch("/{feature_id}", response_model=schemas.AssessmentFeatureRead)
async def update_assessment_feature(
    assessment_id: str,
    feature_id: str,
    payload: schemas.AssessmentFeatureUpdate,
    # ... similar to above
) -> schemas.AssessmentFeatureRead:
    # Update feature


@router.delete("/{feature_id}", status_code=204)
async def delete_assessment_feature(
    assessment_id: str,
    feature_id: str,
    # ... similar to above
) -> None:
    # Delete feature (cascade will delete scores)
```

#### 2. Review Feature Scores (`backend/app/routes/reviews.py` - extend existing)

Add endpoints to existing reviews router:

```python
@router.post("/{invitation_id}/feature-scores", response_model=schemas.ReviewFeatureScoreRead, status_code=201)
async def create_review_feature_score(
    invitation_id: str,
    payload: schemas.ReviewFeatureScoreCreate,
    session: AsyncSession = Depends(get_session),
    current_session: SupabaseSession = Depends(require_roles("authenticated", "service_role")),
) -> schemas.ReviewFeatureScoreRead:
    # Verify invitation exists and user has access
    # Create or update score
    # Return score


@router.get("/{invitation_id}/feature-scores", response_model=List[schemas.ReviewFeatureScoreRead])
async def list_review_feature_scores(
    invitation_id: str,
    session: AsyncSession = Depends(get_session),
    current_session: SupabaseSession = Depends(require_roles("authenticated", "service_role")),
) -> List[schemas.ReviewFeatureScoreRead]:
    # List all feature scores for invitation


@router.patch("/{invitation_id}/feature-scores/{score_id}", response_model=schemas.ReviewFeatureScoreRead)
async def update_review_feature_score(
    invitation_id: str,
    score_id: str,
    payload: schemas.ReviewFeatureScoreUpdate,
    # ... similar to above
) -> schemas.ReviewFeatureScoreRead:
    # Update score


@router.get("/{invitation_id}/score-summary", response_model=schemas.ReviewScoreSummary)
async def get_review_score_summary(
    invitation_id: str,
    session: AsyncSession = Depends(get_session),
    current_session: SupabaseSession = Depends(require_roles("authenticated", "service_role")),
) -> schemas.ReviewScoreSummary:
    # Calculate and return score summary
    # Join features and scores, calculate totals
```

#### 3. Update Assessment endpoints

Update `assessments.py` to handle `rubric_text` in create/update operations.

### Utility Functions

Add score calculation helper:

```python
async def calculate_invitation_score(
    session: AsyncSession,
    invitation_id: uuid.UUID,
) -> schemas.ReviewScoreSummary:
    """Calculate total score for an invitation based on checked features."""
    # Query invitation and assessment
    # Get all features for assessment
    # Get all scores for invitation
    # Calculate: sum(checked_features.weight) / sum(all_features.weight) * 100
    # Return summary
```

---

## Frontend Implementation

### TypeScript Types (`frontend/lib/types.ts`)

Add new types:

```typescript
export type AssessmentFeature = {
  id: string;
  assessmentId: string;
  name: string;
  description: string | null;
  weight: number;
  displayOrder: number;
  createdAt: string;
};

export type ReviewFeatureScore = {
  id: string;
  invitationId: string;
  featureId: string;
  checked: boolean;
  createdBy: string | null;
  createdAt: string;
  updatedAt: string;
};

export type ReviewScoreSummary = {
  invitationId: string;
  totalScore: number;
  maxScore: number;
  percentage: number;
  features: Array<{
    featureId: string;
    name: string;
    weight: number;
    checked: boolean;
    score: number;
  }>;
};

// Update Assessment type
export type Assessment = {
  // ... existing fields ...
  rubricText: string | null;
};
```

### API Functions (`frontend/lib/api.ts`)

Add API functions:

```typescript
// Assessment Features
export async function createAssessmentFeature(
  assessmentId: string,
  payload: { name: string; description?: string; weight: number; displayOrder: number },
  options: ApiRequestOptions = {},
): Promise<AssessmentFeature>;

export async function listAssessmentFeatures(
  assessmentId: string,
  options: ApiRequestOptions = {},
): Promise<AssessmentFeature[]>;

export async function updateAssessmentFeature(
  assessmentId: string,
  featureId: string,
  payload: Partial<{ name: string; description: string; weight: number; displayOrder: number }>,
  options: ApiRequestOptions = {},
): Promise<AssessmentFeature>;

export async function deleteAssessmentFeature(
  assessmentId: string,
  featureId: string,
  options: ApiRequestOptions = {},
): Promise<void>;

// Review Feature Scores
export async function upsertReviewFeatureScore(
  invitationId: string,
  payload: { featureId: string; checked: boolean },
  options: ApiRequestOptions = {},
): Promise<ReviewFeatureScore>;

export async function listReviewFeatureScores(
  invitationId: string,
  options: ApiRequestOptions = {},
): Promise<ReviewFeatureScore[]>;

export async function getReviewScoreSummary(
  invitationId: string,
  options: ApiRequestOptions = {},
): Promise<ReviewScoreSummary>;
```

### UI Components

#### 1. Assessment Detail Page - Rubric Editor
**Location**: `frontend/app/app/(admin)/dashboard/assessments/[assessmentId]/page.tsx`

Add a new section or tab for:
- Rubric text editor (textarea/markdown editor)
- Save/update rubric button
- Preview of rubric (rendered markdown)

#### 2. Assessment Detail Page - Features Manager
**Location**: Same as above

Add section for:
- List of features with edit/delete buttons
- "Add Feature" button/modal
- Feature form: name, description, weight input, display order
- Drag-and-drop or up/down arrows for reordering (nice-to-have)

#### 3. Review Page - Rubric Display
**Location**: `frontend/app/app/(admin)/review/[invitationId]/page.tsx`

In the "Summary" or new "Scoring" tab:
- Display rubric text (rendered markdown)
- Display all features as checkboxes
- Show weight next to each feature
- Real-time score calculation as checkboxes are toggled
- Score summary card showing:
  - Total Score / Max Score
  - Percentage
  - Breakdown by feature

#### 4. Review Page - Feature Checklist
**Location**: Same as above

Component structure:
```
<Card>
  <CardHeader>
    <CardTitle>Scoring Rubric</CardTitle>
    <CardDescription>Check off features that are implemented</CardDescription>
  </CardHeader>
  <CardContent>
    {assessment.rubricText && (
      <div className="prose">
        <Markdown>{assessment.rubricText}</Markdown>
      </div>
    )}
    <div className="space-y-3 mt-4">
      {features.map(feature => (
        <FeatureCheckbox
          key={feature.id}
          feature={feature}
          checked={scores.find(s => s.featureId === feature.id)?.checked ?? false}
          onToggle={handleToggle}
          weight={feature.weight}
        />
      ))}
    </div>
    <ScoreSummaryCard summary={scoreSummary} />
  </CardContent>
</Card>
```

### Component: FeatureCheckbox

```typescript
function FeatureCheckbox({
  feature,
  checked,
  onToggle,
  weight,
}: {
  feature: AssessmentFeature;
  checked: boolean;
  onToggle: (featureId: string, checked: boolean) => void;
  weight: number;
}) {
  return (
    <div className="flex items-start gap-3 p-3 border rounded-lg">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onToggle(feature.id, e.target.checked)}
        className="mt-1"
      />
      <div className="flex-1">
        <label className="font-medium">{feature.name}</label>
        {feature.description && (
          <p className="text-sm text-zinc-600 mt-1">{feature.description}</p>
        )}
      </div>
      <Badge variant="outline">Weight: {weight}</Badge>
    </div>
  );
}
```

### Component: ScoreSummaryCard

```typescript
function ScoreSummaryCard({ summary }: { summary: ReviewScoreSummary }) {
  return (
    <Card className="mt-6">
      <CardHeader>
        <CardTitle>Score Summary</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-2">
          <div className="flex justify-between">
            <span>Score:</span>
            <span className="font-semibold">
              {summary.totalScore.toFixed(2)} / {summary.maxScore.toFixed(2)}
            </span>
          </div>
          <div className="flex justify-between">
            <span>Percentage:</span>
            <span className="font-semibold">{summary.percentage.toFixed(1)}%</span>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
```

---

## Implementation Steps

### Phase 1: Database & Backend Foundation
1. ✅ Create migration for `rubric_text` on assessments
2. ✅ Create migration for `assessment_features` table
3. ✅ Create migration for `review_feature_scores` table
4. ✅ Add models to `models.py`
5. ✅ Add schemas to `schemas.py`
6. ✅ Update `Assessment` model/schema to include `rubric_text`

### Phase 2: Backend API
7. ✅ Create `routes/assessment_features.py` router
8. ✅ Add feature CRUD endpoints
9. ✅ Add review scoring endpoints to `routes/reviews.py`
10. ✅ Add score calculation utility
11. ✅ Update assessment endpoints to handle `rubric_text`
12. ✅ Register new routers in `main.py`

### Phase 3: Frontend Types & API
13. ✅ Add TypeScript types
14. ✅ Add API functions for features
15. ✅ Add API functions for scores

### Phase 4: Frontend UI - Assessment Management
16. ✅ Add rubric editor to assessment detail page
17. ✅ Add features manager to assessment detail page
18. ✅ Add feature creation/edit modals

### Phase 5: Frontend UI - Review Interface
19. ✅ Add rubric display to review page
20. ✅ Add feature checklist component
21. ✅ Add score summary display
22. ✅ Implement real-time score updates

### Phase 6: Testing & Polish
23. ✅ Test end-to-end flow
24. ✅ Handle edge cases (no features, no scores, etc.)
25. ✅ Add loading states
26. ✅ Add error handling
27. ✅ Add validation (weights >= 0, etc.)

---

## Edge Cases & Considerations

1. **No features defined**: Show message "No scoring features defined for this assessment"
2. **Feature deleted after scores exist**: Cascade delete handles this, but show warning in UI
3. **Multiple reviewers**: Scores are per-invitation, not per-reviewer. Consider if you want per-reviewer scoring (would need `created_by` logic)
4. **Weight changes**: If weights change after scoring, historical scores may not match. Option to recalculate or store historical weights
5. **Empty rubric**: Allow empty/null rubric text
6. **Feature ordering**: Use `display_order` field, allow drag-and-drop in future
7. **Score display format**: Decide on decimal places (2 seems reasonable)

---

## Future Enhancements (Out of Scope)

1. **Per-reviewer scoring**: Track scores separately for each reviewer
2. **Feature categories/groups**: Group features into categories
3. **Partial scores**: Instead of boolean checked, allow 0-100% completion
4. **Comments per feature**: Add text comments for each feature
5. **Score history**: Track score changes over time
6. **Comparison view**: Compare scores across candidates
7. **Export scores**: CSV/PDF export of scores
8. **Rubric templates**: Reusable rubric templates across assessments

---

## Database Migration File

Create: `backend/db/migrations/add_ranking_scoring_features.sql`

```sql
-- Add rubric_text to assessments
ALTER TABLE assessments
  ADD COLUMN IF NOT EXISTS rubric_text text;

-- Create assessment_features table
CREATE TABLE IF NOT EXISTS assessment_features (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  assessment_id uuid REFERENCES assessments(id) ON DELETE CASCADE NOT NULL,
  name text NOT NULL,
  description text,
  weight decimal(10, 2) NOT NULL DEFAULT 1.0,
  display_order integer NOT NULL DEFAULT 0,
  created_at timestamptz DEFAULT now(),
  UNIQUE (assessment_id, name)
);
CREATE INDEX IF NOT EXISTS idx_assessment_features_assessment_id 
  ON assessment_features(assessment_id);

-- Create review_feature_scores table
CREATE TABLE IF NOT EXISTS review_feature_scores (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  invitation_id uuid REFERENCES invitations(id) ON DELETE CASCADE NOT NULL,
  feature_id uuid REFERENCES assessment_features(id) ON DELETE CASCADE NOT NULL,
  checked boolean NOT NULL DEFAULT false,
  created_by uuid,
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now(),
  UNIQUE (invitation_id, feature_id)
);
CREATE INDEX IF NOT EXISTS idx_review_feature_scores_invitation_id 
  ON review_feature_scores(invitation_id);
CREATE INDEX IF NOT EXISTS idx_review_feature_scores_feature_id 
  ON review_feature_scores(feature_id);

-- Optional: Add score tracking to review_feedback
ALTER TABLE review_feedback
  ADD COLUMN IF NOT EXISTS calculated_score decimal(10, 2),
  ADD COLUMN IF NOT EXISTS max_score decimal(10, 2);
```

---

This plan provides a comprehensive roadmap for implementing the ranking and scoring feature. Each phase can be implemented incrementally, and the design allows for future enhancements.



