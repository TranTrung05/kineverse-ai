//! GestureEngine state machine and dynamic swipe detection.

use crate::features::clip;
use crate::types::{
    EngineState, GestureAction, GestureConfig, GestureLabel, RawGestureEvent,
};
use std::collections::VecDeque;

const MAX_ACTIONS: usize = 16;

pub struct GestureEngine {
    pub cfg: GestureConfig,
    pub state: EngineState,
    pub current: GestureLabel,
    cand: GestureLabel,
    cand_n: u32,
    active: bool,
    lost: u32,
    last_fire: [f64; MAX_ACTIONS],
    hist: VecDeque<(f64, f32, f32)>,
    pub suppressed: u32,
    pub grab_fired: bool,
}

impl GestureEngine {
    pub fn new(cfg: GestureConfig) -> Self {
        Self {
            cfg,
            state: EngineState::NoHand,
            current: GestureLabel::Unknown,
            cand: GestureLabel::Unknown,
            cand_n: 0,
            active: false,
            lost: 0,
            last_fire: [-1e9; MAX_ACTIONS],
            hist: VecDeque::with_capacity(32),
            suppressed: 0,
            grab_fired: false,
        }
    }

    #[inline(always)]
    pub fn is_pinching(&self) -> bool {
        self.current == GestureLabel::Pinch
    }

    #[inline(always)]
    pub fn is_grabbing(&self) -> bool {
        self.current == GestureLabel::Pinch && self.grab_fired
    }

    fn frames_needed(&self, label: GestureLabel) -> u32 {
        let n = self.cfg.stable_frames;
        if self.current == GestureLabel::Pinch && label != GestureLabel::Pinch {
            if label == GestureLabel::Fist {
                self.cfg.fist_after_pinch_frames.max(n)
            } else {
                self.cfg.release_frames.max(n)
            }
        } else {
            n
        }
    }

    fn cooldown(&self, action: GestureAction) -> f64 {
        match action {
            GestureAction::Grab => self.cfg.grab_cooldown_s as f64,
            GestureAction::MoveLeft
            | GestureAction::MoveRight
            | GestureAction::MoveUp
            | GestureAction::MoveDown => self.cfg.swipe_cooldown_s as f64,
            _ => self.cfg.default_cooldown_s as f64,
        }
    }

    fn fire(
        &mut self,
        label: GestureLabel,
        action: GestureAction,
        conf: f32,
        is_dynamic: bool,
        t: f64,
        dist: f32,
    ) -> Option<RawGestureEvent> {
        let idx = action as usize;
        if action != GestureAction::Release && idx < MAX_ACTIONS {
            let last = self.last_fire[idx];
            if last >= 0.0 && (t - last) < self.cooldown(action) {
                self.suppressed += 1;
                return None;
            }
            self.last_fire[idx] = t;
        } else if idx < MAX_ACTIONS {
            self.last_fire[idx] = t;
        }

        Some(RawGestureEvent {
            label,
            action,
            confidence: conf,
            is_dynamic,
            timestamp: t,
            dist,
        })
    }

    /// Process static gesture classification for this frame
    pub fn process_static(
        &mut self,
        mut label: GestureLabel,
        conf: f32,
        t: f64,
        out_events: &mut Vec<RawGestureEvent>,
    ) {
        if self.state == EngineState::NoHand {
            self.state = if self.active {
                EngineState::Active
            } else {
                EngineState::Idle
            };
        }
        self.lost = 0;

        if conf < self.cfg.min_confidence {
            label = GestureLabel::Unknown;
        }

        if label == self.cand {
            self.cand_n += 1;
        } else {
            self.cand = label;
            self.cand_n = 1;
        }

        if self.cand_n >= self.frames_needed(label) && label != self.current {
            let prev = self.current;
            self.current = label;

            if prev == GestureLabel::Pinch {
                self.grab_fired = false;
                if let Some(ev) =
                    self.fire(GestureLabel::Pinch, GestureAction::Release, conf, false, t, 0.0)
                {
                    out_events.push(ev);
                }
            }

            let action = label.to_action();
            if action != GestureAction::None {
                if let Some(ev) = self.fire(label, action, conf, false, t, 0.0) {
                    out_events.push(ev);
                    match action {
                        GestureAction::Grab => self.grab_fired = true,
                        GestureAction::Activate => self.active = true,
                        GestureAction::Cancel => self.active = false,
                        _ => {}
                    }
                }
            }

            self.state = if self.current == GestureLabel::Pinch {
                EngineState::Grabbing
            } else if self.active {
                EngineState::Active
            } else {
                EngineState::Idle
            };
        }

        if self.current != GestureLabel::OpenPalm {
            self.hist.clear();
        }
    }

    /// Detect dynamic swipe gestures from palm center movement
    pub fn process_motion(&mut self, x: f32, y: f32, t: f64, out_events: &mut Vec<RawGestureEvent>) {
        if self.current != GestureLabel::OpenPalm || self.state == EngineState::Grabbing {
            self.hist.clear();
            return;
        }

        self.hist.push_back((t, x, y));
        while let Some(&(t0, _, _)) = self.hist.front() {
            if (t - t0) > self.cfg.swipe_window_s as f64 {
                self.hist.pop_front();
            } else {
                break;
            }
        }

        if self.hist.len() < 3 {
            return;
        }

        let (t0, x0, y0) = *self.hist.front().unwrap();
        let dx = x - x0;
        let dy = y - y0;
        let dt = (t - t0) as f32;
        let dist = (dx * dx + dy * dy).sqrt();

        if dt < 0.08 || dist < self.cfg.swipe_min_dist || (dist / dt) < self.cfg.swipe_min_speed {
            return;
        }

        let ax = dx.abs();
        let ay = dy.abs();
        if ax.max(ay) < self.cfg.swipe_axis_ratio * ax.min(ay) {
            return; // Diagonal movement, discard
        }

        let action = if ax > ay {
            if dx > 0.0 {
                GestureAction::MoveRight
            } else {
                GestureAction::MoveLeft
            }
        } else if dy > 0.0 {
            GestureAction::MoveDown
        } else {
            GestureAction::MoveUp
        };

        let conf = clip(
            0.7 + 0.3 * (dist / (2.0 * self.cfg.swipe_min_dist)).min(1.0),
            0.0,
            1.0,
        );

        if let Some(ev) = self.fire(GestureLabel::OpenPalm, action, conf, true, t, dist) {
            out_events.push(ev);
        }
        self.hist.clear();
    }

    /// Hand lost callback
    pub fn on_hand_lost(&mut self, t: f64, out_events: &mut Vec<RawGestureEvent>) -> bool {
        if self.state == EngineState::NoHand {
            return false;
        }
        self.lost += 1;
        if self.lost < self.cfg.lost_hand_frames {
            return false;
        }

        if self.current == GestureLabel::Pinch {
            out_events.push(RawGestureEvent {
                label: GestureLabel::Pinch,
                action: GestureAction::Release,
                confidence: 1.0,
                is_dynamic: false,
                timestamp: t,
                dist: 0.0,
            });
        }

        self.grab_fired = false;
        self.state = EngineState::NoHand;
        self.current = GestureLabel::Unknown;
        self.cand = GestureLabel::Unknown;
        self.cand_n = 0;
        self.hist.clear();
        true
    }
}
