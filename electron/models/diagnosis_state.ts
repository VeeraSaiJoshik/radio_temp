export interface Circle {
    x: number;
    y: number;
    radius: number;
    color: string;
}

export interface Rectangle {
    x: number;
    y: number;
    width: number;
    height: number;
    color: string;
}

export interface Annotation {
    name: string;
    description: string;
    number: number;
    annotations: Array<Rectangle | Circle>
    confidence: string;
}

export interface MedicalModel {
    name: string;
    provider: string
    description: string;
}

export interface ModelNode {
    status: "pending" | "positive" | "negative" | "in-progress";
    children: ModelNode[];
    model: MedicalModel;
}

export interface DiagnosisState {
    diagnosis_id: string;
    progress_tree: ModelNode;
    percent_completion: number;
    annotations: Annotation[];
    overall_diagnosis_context: string;
}