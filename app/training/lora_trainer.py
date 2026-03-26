"""
LoRA Fine-Tuning Pipeline for MedGemma (Phase 3)

Takes clinician correction feedback and fine-tunes MedGemma using
PEFT/LoRA for improved SOAP note generation quality.

Architecture:
    Feedback JSONL → Dataset Preparation → LoRA Training → Evaluation → Adapter Export

Config:
    - LoRA rank: 16
    - LoRA alpha: 32
    - Target modules: q_proj, v_proj (attention layers)
    - Learning rate: 2e-4
    - Training epochs: 3
    - Batch size: 4
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.config import settings

logger = logging.getLogger(__name__)

_TRAINING_OUTPUT_DIR = "training_data/lora_adapters"
_DATASET_DIR = "training_data/datasets"


@dataclass
class LoRAConfig:
    """Configuration for LoRA fine-tuning."""

    rank: int = 16
    alpha: int = 32
    dropout: float = 0.05
    target_modules: List[str] = field(
        default_factory=lambda: ["q_proj", "v_proj"]
    )
    learning_rate: float = 2e-4
    num_epochs: int = 3
    batch_size: int = 4
    gradient_accumulation_steps: int = 4
    warmup_ratio: float = 0.1
    max_seq_length: int = 1024
    eval_split: float = 0.1  # 10% for evaluation


@dataclass
class TrainingResult:
    """Result of a LoRA training run."""

    adapter_path: str = ""
    total_samples: int = 0
    train_samples: int = 0
    eval_samples: int = 0
    train_loss: float = 0.0
    eval_loss: float = 0.0
    training_time_seconds: float = 0.0
    improvement_metrics: Dict[str, float] = field(default_factory=dict)


class LoRATrainer:
    """Manages LoRA fine-tuning of MedGemma on clinician feedback."""

    def __init__(self, config: Optional[LoRAConfig] = None):
        self.config = config or LoRAConfig()
        self._output_dir = Path(_TRAINING_OUTPUT_DIR)
        self._dataset_dir = Path(_DATASET_DIR)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._dataset_dir.mkdir(parents=True, exist_ok=True)

    def prepare_dataset(
        self,
        feedback_entries: Optional[List[Any]] = None,
    ) -> Tuple[str, int]:
        """Convert clinician feedback into instruction-tuning format.

        Format per sample:
        {
            "instruction": "Generate a SOAP {section} note for...",
            "input": "{transcript + context}",
            "output": "{corrected_text}"
        }

        Args:
            feedback_entries: List of ClinicalFeedback. If None, loads from disk.

        Returns:
            Tuple of (dataset_path, sample_count).
        """
        if feedback_entries is None:
            from app.training.feedback_collector import get_feedback_collector
            collector = get_feedback_collector()
            feedback_entries = collector.get_all_feedback()

        if not feedback_entries:
            logger.warning("No feedback entries to prepare dataset from")
            return "", 0

        # Filter to entries with actual corrections
        valid = [
            e for e in feedback_entries
            if e.correction_type in ("edit", "minor_fix", "reject")
            and e.corrected_text.strip()
            and e.original_text.strip() != e.corrected_text.strip()
        ]

        if not valid:
            logger.warning("No valid corrections found in feedback")
            return "", 0

        dataset_path = self._dataset_dir / f"lora_dataset_{int(time.time())}.jsonl"

        with open(dataset_path, "w", encoding="utf-8") as f:
            for entry in valid:
                sample = self._format_training_sample(entry)
                f.write(json.dumps(sample) + "\n")

        logger.info(
            f"Prepared LoRA dataset: {len(valid)} samples at {dataset_path}"
        )
        return str(dataset_path), len(valid)

    def _format_training_sample(self, feedback) -> Dict[str, str]:
        """Format a single feedback entry as an instruction-tuning sample."""
        section_name = feedback.soap_section.replace("_", " ").title()
        specialty_ctx = (
            f" (Specialty: {feedback.specialty})"
            if feedback.specialty != "general"
            else ""
        )

        instruction = (
            f"Generate the SOAP {section_name} section for the following "
            f"patient encounter{specialty_ctx}. Write a concise, clinical-style "
            f"paragraph using plain English."
        )

        input_text = f"Patient transcript: {feedback.transcript}"
        if feedback.chief_complaint:
            input_text += f"\nChief complaint: {feedback.chief_complaint}"

        return {
            "instruction": instruction,
            "input": input_text,
            "output": feedback.corrected_text,
        }

    def train(
        self,
        dataset_path: str,
        model_name: Optional[str] = None,
        output_name: Optional[str] = None,
    ) -> TrainingResult:
        """Run LoRA fine-tuning on the prepared dataset.

        Requires: transformers, peft, trl, datasets

        Args:
            dataset_path: Path to JSONL dataset.
            model_name: Base model to fine-tune (default: settings.medgemma_model).
            output_name: Name for the output adapter directory.

        Returns:
            TrainingResult with metrics and adapter path.
        """
        model_name = model_name or settings.medgemma_model
        output_name = output_name or f"lora_adapter_{int(time.time())}"
        adapter_path = str(self._output_dir / output_name)

        start_time = time.time()

        try:
            return self._run_training(
                dataset_path, model_name, adapter_path
            )
        except ImportError as e:
            logger.error(
                f"Missing dependency for LoRA training: {e}. "
                "Install with: pip install peft>=0.11.0 trl>=0.9.0 datasets>=2.19.0"
            )
            return TrainingResult(
                adapter_path="",
                training_time_seconds=time.time() - start_time,
            )
        except Exception as e:
            logger.error(f"LoRA training failed: {e}")
            return TrainingResult(
                adapter_path="",
                training_time_seconds=time.time() - start_time,
            )

    def _run_training(
        self,
        dataset_path: str,
        model_name: str,
        adapter_path: str,
    ) -> TrainingResult:
        """Execute the actual LoRA training loop."""
        import torch
        from datasets import load_dataset
        from peft import LoraConfig, get_peft_model, TaskType
        from transformers import (
            AutoModelForCausalLM,
            AutoTokenizer,
            TrainingArguments,
        )
        from trl import SFTTrainer

        start_time = time.time()

        # Load dataset
        dataset = load_dataset("json", data_files=dataset_path, split="train")
        total_samples = len(dataset)

        # Train/eval split
        eval_size = max(1, int(total_samples * self.config.eval_split))
        split = dataset.train_test_split(test_size=eval_size, seed=42)
        train_dataset = split["train"]
        eval_dataset = split["test"]

        logger.info(
            f"Dataset loaded: {len(train_dataset)} train, "
            f"{len(eval_dataset)} eval samples"
        )

        # Load tokenizer and model
        tokenizer = AutoTokenizer.from_pretrained(
            model_name,
            token=settings.hf_token if settings.hf_token else None,
        )
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token

        dtype = torch.bfloat16 if torch.cuda.is_available() else torch.float32

        model = AutoModelForCausalLM.from_pretrained(
            model_name,
            torch_dtype=dtype,
            device_map="auto" if torch.cuda.is_available() else None,
            token=settings.hf_token if settings.hf_token else None,
            low_cpu_mem_usage=True,
        )

        # Apply LoRA
        lora_config = LoraConfig(
            task_type=TaskType.CAUSAL_LM,
            r=self.config.rank,
            lora_alpha=self.config.alpha,
            lora_dropout=self.config.dropout,
            target_modules=self.config.target_modules,
            bias="none",
        )
        model = get_peft_model(model, lora_config)
        model.print_trainable_parameters()

        # Format samples for SFT
        def format_sample(example):
            return {
                "text": (
                    f"### Instruction:\n{example['instruction']}\n\n"
                    f"### Input:\n{example['input']}\n\n"
                    f"### Response:\n{example['output']}"
                )
            }

        train_dataset = train_dataset.map(format_sample)
        eval_dataset = eval_dataset.map(format_sample)

        # Training arguments
        training_args = TrainingArguments(
            output_dir=adapter_path,
            num_train_epochs=self.config.num_epochs,
            per_device_train_batch_size=self.config.batch_size,
            gradient_accumulation_steps=self.config.gradient_accumulation_steps,
            learning_rate=self.config.learning_rate,
            warmup_ratio=self.config.warmup_ratio,
            logging_steps=10,
            save_strategy="epoch",
            evaluation_strategy="epoch",
            bf16=torch.cuda.is_available(),
            report_to="none",
            remove_unused_columns=False,
        )

        # Trainer
        trainer = SFTTrainer(
            model=model,
            args=training_args,
            train_dataset=train_dataset,
            eval_dataset=eval_dataset,
            tokenizer=tokenizer,
            dataset_text_field="text",
            max_seq_length=self.config.max_seq_length,
        )

        # Train
        train_result = trainer.train()

        # Save adapter
        model.save_pretrained(adapter_path)
        tokenizer.save_pretrained(adapter_path)

        # Eval
        eval_result = trainer.evaluate()

        training_time = time.time() - start_time

        result = TrainingResult(
            adapter_path=adapter_path,
            total_samples=total_samples,
            train_samples=len(train_dataset),
            eval_samples=len(eval_dataset),
            train_loss=train_result.training_loss,
            eval_loss=eval_result.get("eval_loss", 0.0),
            training_time_seconds=training_time,
        )

        logger.info(
            f"LoRA training complete: {result.train_samples} samples, "
            f"train_loss={result.train_loss:.4f}, "
            f"eval_loss={result.eval_loss:.4f}, "
            f"adapter saved to {adapter_path}"
        )

        return result

    def load_adapter(self, adapter_path: str) -> None:
        """Load a trained LoRA adapter into the active MedGemma model.

        This merges the adapter weights for inference without modifying
        the base model weights on disk.
        """
        try:
            from peft import PeftModel
            from app.models.medgemma_service import get_medgemma_service

            medgemma = get_medgemma_service()
            if medgemma.model is None:
                logger.error("MedGemma model not loaded, cannot apply LoRA adapter")
                return

            medgemma.model = PeftModel.from_pretrained(
                medgemma.model,
                adapter_path,
            )
            medgemma.model.eval()
            logger.info(f"LoRA adapter loaded from {adapter_path}")

        except ImportError:
            logger.error("peft not installed. Cannot load LoRA adapter.")
        except Exception as e:
            logger.error(f"Failed to load LoRA adapter: {e}")

    def list_adapters(self) -> List[Dict[str, Any]]:
        """List all saved LoRA adapters."""
        adapters = []
        for path in sorted(self._output_dir.iterdir()):
            if path.is_dir() and (path / "adapter_config.json").exists():
                config = json.loads((path / "adapter_config.json").read_text())
                adapters.append({
                    "name": path.name,
                    "path": str(path),
                    "rank": config.get("r", "unknown"),
                    "alpha": config.get("lora_alpha", "unknown"),
                    "target_modules": config.get("target_modules", []),
                })
        return adapters


# Singleton
_trainer: Optional[LoRATrainer] = None


def get_lora_trainer() -> LoRATrainer:
    global _trainer
    if _trainer is None:
        _trainer = LoRATrainer()
    return _trainer
