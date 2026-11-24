//! Core types for Kineverse gesture processing.

pub const NUM_LANDMARKS: usize = 21;
pub const TIPS: [usize; 4] = [8, 12, 16, 20];
pub const MCPS: [usize; 4] = [5, 9, 13, 17];

/// Point in 3D normalized space (MediaPipe format: x, y, z)
#[derive(Debug, Clone, Copy, PartialEq, Default)]
#[repr(C)]
pub struct Point3D {
    pub x: f32,
    pub y: f32,
    pub z: f32,
}

impl Point3D {
    #[inline(always)]
    pub fn new(x: f32, y: f32, z: f32) -> Self {
        Self { x, y, z }
    }

    #[inline(always)]
    pub fn distance_to(&self, other: &Point3D) -> f32 {
        let dx = self.x - other.x;
        let dy = self.y - other.y;
        let dz = self.z - other.z;
        (dx * dx + dy * dy + dz * dz).sqrt()
    }

    #[inline(always)]
    pub fn norm(&self) -> f32 {
        (self.x * self.x + self.y * self.y + self.z * self.z).sqrt()
    }
}

/// Static gesture labels
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
#[repr(u8)]
pub enum GestureLabel {
    #[default]
    Unknown = 0,
    OpenPalm = 1,
    Pinch = 2,
    Fist = 3,
    Pointing = 4,
    TwoFingers = 5,
}

impl GestureLabel {
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::OpenPalm => "OPEN_PALM",
            Self::Pinch => "PINCH",
            Self::Fist => "FIST",
            Self::Pointing => "POINTING",
            Self::TwoFingers => "TWO_FINGERS",
            Self::Unknown => "UNKNOWN",
        }
    }

    pub fn to_action(&self) -> GestureAction {
        match self {
            Self::OpenPalm => GestureAction::Activate,
            Self::Pinch => GestureAction::Grab,
            Self::Fist => GestureAction::Cancel,
            Self::Pointing => GestureAction::Select,
            Self::TwoFingers => GestureAction::SwitchMode,
            Self::Unknown => GestureAction::None,
        }
    }
}

/// Interaction action dispatched to Unity or UI
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
#[repr(u8)]
pub enum GestureAction {
    #[default]
    None = 0,
    Activate = 1,
    Select = 2,
    Grab = 3,
    Release = 4,
    MoveLeft = 5,
    MoveRight = 6,
    MoveUp = 7,
    MoveDown = 8,
    Move = 9,
    Rotate = 10,
    Scale = 11,
    SwitchMode = 12,
    Cancel = 13,
    Reset = 14,
}

impl GestureAction {
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::None => "NONE",
            Self::Activate => "ACTIVATE",
            Self::Select => "SELECT",
            Self::Grab => "GRAB",
            Self::Release => "RELEASE",
            Self::MoveLeft => "MOVE_LEFT",
            Self::MoveRight => "MOVE_RIGHT",
            Self::MoveUp => "MOVE_UP",
            Self::MoveDown => "MOVE_DOWN",
            Self::Move => "MOVE",
            Self::Rotate => "ROTATE",
            Self::Scale => "SCALE",
            Self::SwitchMode => "SWITCH_MODE",
            Self::Cancel => "CANCEL",
            Self::Reset => "RESET",
        }
    }
}

/// Gesture Engine operational state
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
#[repr(u8)]
pub enum EngineState {
    #[default]
    NoHand = 0,
    Idle = 1,
    Active = 2,
    Grabbing = 3,
}

impl EngineState {
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::NoHand => "NO_HAND",
            Self::Idle => "IDLE",
            Self::Active => "ACTIVE",
            Self::Grabbing => "GRABBING",
        }
    }
}

/// Configuration parameters for gesture recognition
#[derive(Debug, Clone, Copy)]
#[repr(C)]
pub struct GestureConfig {
    pub min_confidence: f32,
    pub stable_frames: u32,
    pub lost_hand_frames: u32,
    pub pinch_on: f32,
    pub pinch_off: f32,
    pub pinch_shape_min: f32,
    pub pinch_shape_hold: f32,
    pub release_frames: u32,
    pub fist_after_pinch_frames: u32,
    pub swipe_window_s: f32,
    pub swipe_min_dist: f32,
    pub swipe_min_speed: f32,
    pub swipe_axis_ratio: f32,
    pub default_cooldown_s: f32,
    pub grab_cooldown_s: f32,
    pub swipe_cooldown_s: f32,
    pub idx_out_lo: f32,
    pub idx_out_span: f32,
    pub reach_lo: f32,
    pub reach_span: f32,
}

impl Default for GestureConfig {
    fn default() -> Self {
        Self {
            min_confidence: 0.60,
            stable_frames: 4,
            lost_hand_frames: 8,
            pinch_on: 0.36,
            pinch_off: 0.50,
            pinch_shape_min: 0.50,
            pinch_shape_hold: 0.25,
            release_frames: 5,
            fist_after_pinch_frames: 8,
            swipe_window_s: 0.35,
            swipe_min_dist: 0.18,
            swipe_min_speed: 0.90,
            swipe_axis_ratio: 1.60,
            default_cooldown_s: 0.60,
            grab_cooldown_s: 0.30,
            swipe_cooldown_s: 0.70,
            idx_out_lo: 0.45,
            idx_out_span: 0.22,
            reach_lo: 0.68,
            reach_span: 0.18,
        }
    }
}

/// Detailed metrics computed during feature extraction
#[derive(Debug, Clone, Copy, Default)]
#[repr(C)]
pub struct FeatureInfo {
    pub ext: [f32; 4],
    pub pinch_ratio: f32,
    pub ring_shape: f32,
}

/// Event emitted by GestureEngine
#[derive(Debug, Clone, Copy)]
#[repr(C)]
pub struct RawGestureEvent {
    pub label: GestureLabel,
    pub action: GestureAction,
    pub confidence: f32,
    pub is_dynamic: bool,
    pub timestamp: f64,
    pub dist: f32,
}
