export interface AudienceReaction {
  audience_type: string;
  likely_reaction: string;
  reasoning: string;
  watch_out: string;
}

export interface SceneAudienceSimulation {
  scene_id: string;
  audience_reactions: AudienceReaction[];
  interpretation_variance: string;
  co_director_note: string;
}

export interface ProjectAudienceSimulation {
  project_id: string;
  audience_reactions: AudienceReaction[];
  scene_simulations: SceneAudienceSimulation[];
  co_director_note: string;
}
