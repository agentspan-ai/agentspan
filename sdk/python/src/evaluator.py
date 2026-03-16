"""
Model evaluation and visualization module for ML training pipeline.
Handles model evaluation, metrics calculation, and result visualization.
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.metrics import confusion_matrix, roc_curve, auc, precision_recall_curve
from sklearn.metrics import classification_report, mean_squared_error, r2_score
import logging
import os
from typing import Dict, Any, List, Optional, Tuple
import warnings
warnings.filterwarnings('ignore')

class ModelEvaluator:
    """Handles model evaluation and visualization."""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize ModelEvaluator with configuration.
        
        Args:
            config: Configuration dictionary containing evaluation parameters
        """
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Set up plotting style
        plt.style.use('default')
        sns.set_palette("husl")
        
    def plot_confusion_matrix(self, y_true: pd.Series, y_pred: np.ndarray, 
                            class_names: Optional[List[str]] = None, 
                            save_path: Optional[str] = None) -> None:
        """
        Plot confusion matrix for classification results.
        
        Args:
            y_true: True labels
            y_pred: Predicted labels
            class_names: Optional list of class names
            save_path: Optional path to save the plot
        """
        self.logger.info("Generating confusion matrix plot...")
        
        # Calculate confusion matrix
        cm = confusion_matrix(y_true, y_pred)
        
        # Handle class names - if None, use default labels or generate from unique values
        if class_names is None:
            # Generate class names from unique values in y_true
            unique_labels = sorted(y_true.unique())
            class_names = [str(label) for label in unique_labels]
        
        # Create plot
        plt.figure(figsize=(8, 6))
        sns.heatmap(cm, annot=True, fmt='d', cmap='Blues', 
                   xticklabels=class_names, yticklabels=class_names)
        plt.title('Confusion Matrix')
        plt.xlabel('Predicted Label')
        plt.ylabel('True Label')
        
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            self.logger.info(f"Confusion matrix saved to: {save_path}")
        
        plt.show()
        plt.close()
    
    def plot_roc_curve(self, y_true: pd.Series, y_pred_proba: np.ndarray, 
                      save_path: Optional[str] = None) -> float:
        """
        Plot ROC curve for binary classification.
        
        Args:
            y_true: True labels
            y_pred_proba: Predicted probabilities
            save_path: Optional path to save the plot
            
        Returns:
            AUC score
        """
        self.logger.info("Generating ROC curve...")
        
        # Calculate ROC curve
        fpr, tpr, _ = roc_curve(y_true, y_pred_proba)
        roc_auc = auc(fpr, tpr)
        
        # Create plot
        plt.figure(figsize=(8, 6))
        plt.plot(fpr, tpr, color='darkorange', lw=2, 
                label=f'ROC curve (AUC = {roc_auc:.2f})')
        plt.plot([0, 1], [0, 1], color='navy', lw=2, linestyle='--')
        plt.xlim([0.0, 1.0])
        plt.ylim([0.0, 1.05])
        plt.xlabel('False Positive Rate')
        plt.ylabel('True Positive Rate')
        plt.title('Receiver Operating Characteristic (ROC) Curve')
        plt.legend(loc="lower right")
        plt.grid(True, alpha=0.3)
        
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            self.logger.info(f"ROC curve saved to: {save_path}")
        
        plt.show()
        plt.close()
        
        return roc_auc
    
    def plot_precision_recall_curve(self, y_true: pd.Series, y_pred_proba: np.ndarray, 
                                   save_path: Optional[str] = None) -> float:
        """
        Plot Precision-Recall curve for binary classification.
        
        Args:
            y_true: True labels
            y_pred_proba: Predicted probabilities
            save_path: Optional path to save the plot
            
        Returns:
            Average precision score
        """
        self.logger.info("Generating Precision-Recall curve...")
        
        # Calculate precision-recall curve
        precision, recall, _ = precision_recall_curve(y_true, y_pred_proba)
        avg_precision = auc(recall, precision)
        
        # Create plot
        plt.figure(figsize=(8, 6))
        plt.plot(recall, precision, color='blue', lw=2,
                label=f'PR curve (AP = {avg_precision:.2f})')
        plt.xlabel('Recall')
        plt.ylabel('Precision')
        plt.title('Precision-Recall Curve')
        plt.legend(loc="lower left")
        plt.grid(True, alpha=0.3)
        
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            self.logger.info(f"Precision-Recall curve saved to: {save_path}")
        
        plt.show()
        plt.close()
        
        return avg_precision
    
    def plot_feature_importance(self, feature_importance_df: pd.DataFrame, 
                              top_n: int = 20, save_path: Optional[str] = None) -> None:
        """
        Plot feature importance.
        
        Args:
            feature_importance_df: DataFrame with feature importance scores
            top_n: Number of top features to display
            save_path: Optional path to save the plot
        """
        if feature_importance_df.empty:
            self.logger.warning("No feature importance data to plot")
            return
        
        self.logger.info(f"Generating feature importance plot (top {top_n})...")
        
        # Get top N features
        top_features = feature_importance_df.head(top_n)
        
        # Create plot
        plt.figure(figsize=(10, 8))
        sns.barplot(data=top_features, x='importance', y='feature', palette='viridis')
        plt.title(f'Top {top_n} Feature Importance')
        plt.xlabel('Importance Score')
        plt.ylabel('Features')
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            self.logger.info(f"Feature importance plot saved to: {save_path}")
        
        plt.show()
        plt.close()
    
    def plot_learning_curve(self, train_scores: List[float], val_scores: List[float], 
                          save_path: Optional[str] = None) -> None:
        """
        Plot learning curve showing training and validation scores.
        
        Args:
            train_scores: Training scores over epochs/iterations
            val_scores: Validation scores over epochs/iterations
            save_path: Optional path to save the plot
        """
        self.logger.info("Generating learning curve...")
        
        epochs = range(1, len(train_scores) + 1)
        
        plt.figure(figsize=(10, 6))
        plt.plot(epochs, train_scores, 'b-', label='Training Score', linewidth=2)
        plt.plot(epochs, val_scores, 'r-', label='Validation Score', linewidth=2)
        plt.title('Learning Curve')
        plt.xlabel('Epoch/Iteration')
        plt.ylabel('Score')
        plt.legend()
        plt.grid(True, alpha=0.3)
        
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            self.logger.info(f"Learning curve saved to: {save_path}")
        
        plt.show()
        plt.close()
    
    def plot_residuals(self, y_true: pd.Series, y_pred: np.ndarray, 
                      save_path: Optional[str] = None) -> None:
        """
        Plot residuals for regression analysis.
        
        Args:
            y_true: True values
            y_pred: Predicted values
            save_path: Optional path to save the plot
        """
        self.logger.info("Generating residuals plot...")
        
        residuals = y_true - y_pred
        
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))
        
        # Residuals vs Predicted
        ax1.scatter(y_pred, residuals, alpha=0.6)
        ax1.axhline(y=0, color='red', linestyle='--')
        ax1.set_xlabel('Predicted Values')
        ax1.set_ylabel('Residuals')
        ax1.set_title('Residuals vs Predicted Values')
        ax1.grid(True, alpha=0.3)
        
        # Histogram of residuals
        ax2.hist(residuals, bins=30, alpha=0.7, edgecolor='black')
        ax2.set_xlabel('Residuals')
        ax2.set_ylabel('Frequency')
        ax2.set_title('Distribution of Residuals')
        ax2.grid(True, alpha=0.3)
        
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            self.logger.info(f"Residuals plot saved to: {save_path}")
        
        plt.show()
        plt.close()
    
    def plot_actual_vs_predicted(self, y_true: pd.Series, y_pred: np.ndarray, 
                                save_path: Optional[str] = None) -> None:
        """
        Plot actual vs predicted values for regression.
        
        Args:
            y_true: True values
            y_pred: Predicted values
            save_path: Optional path to save the plot
        """
        self.logger.info("Generating actual vs predicted plot...")
        
        plt.figure(figsize=(8, 8))
        plt.scatter(y_true, y_pred, alpha=0.6)
        
        # Perfect prediction line
        min_val = min(min(y_true), min(y_pred))
        max_val = max(max(y_true), max(y_pred))
        plt.plot([min_val, max_val], [min_val, max_val], 'r--', lw=2)
        
        plt.xlabel('Actual Values')
        plt.ylabel('Predicted Values')
        plt.title('Actual vs Predicted Values')
        plt.grid(True, alpha=0.3)
        
        # Add R² score to the plot
        r2 = r2_score(y_true, y_pred)
        plt.text(0.05, 0.95, f'R² = {r2:.3f}', transform=plt.gca().transAxes, 
                bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
        
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            self.logger.info(f"Actual vs predicted plot saved to: {save_path}")
        
        plt.show()
        plt.close()
    
    def generate_evaluation_report(self, y_true: pd.Series, y_pred: np.ndarray, 
                                 y_pred_proba: Optional[np.ndarray] = None,
                                 feature_importance_df: Optional[pd.DataFrame] = None,
                                 is_classifier: bool = True) -> Dict[str, Any]:
        """
        Generate comprehensive evaluation report with plots.
        
        Args:
            y_true: True labels/values
            y_pred: Predicted labels/values
            y_pred_proba: Predicted probabilities (for classification)
            feature_importance_df: Feature importance DataFrame
            is_classifier: Whether this is a classification task
            
        Returns:
            Dictionary containing evaluation results
        """
        self.logger.info("Generating comprehensive evaluation report...")
        
        # Create plots directory
        plot_dir = self.config['evaluation']['plot_save_path']
        os.makedirs(plot_dir, exist_ok=True)
        
        evaluation_results = {}
        
        if is_classifier:
            # Classification evaluation
            self.logger.info("Performing classification evaluation...")
            
            # Confusion Matrix
            cm_path = os.path.join(plot_dir, 'confusion_matrix.png')
            self.plot_confusion_matrix(y_true, y_pred, save_path=cm_path)
            
            # ROC Curve (for binary classification)
            if len(y_true.unique()) == 2 and y_pred_proba is not None:
                roc_path = os.path.join(plot_dir, 'roc_curve.png')
                auc_score = self.plot_roc_curve(y_true, y_pred_proba[:, 1], save_path=roc_path)
                evaluation_results['auc_score'] = auc_score
                
                # Precision-Recall Curve
                pr_path = os.path.join(plot_dir, 'precision_recall_curve.png')
                avg_precision = self.plot_precision_recall_curve(y_true, y_pred_proba[:, 1], save_path=pr_path)
                evaluation_results['avg_precision'] = avg_precision
            
        else:
            # Regression evaluation
            self.logger.info("Performing regression evaluation...")
            
            # Residuals plot
            residuals_path = os.path.join(plot_dir, 'residuals.png')
            self.plot_residuals(y_true, y_pred, save_path=residuals_path)
            
            # Actual vs Predicted
            actual_pred_path = os.path.join(plot_dir, 'actual_vs_predicted.png')
            self.plot_actual_vs_predicted(y_true, y_pred, save_path=actual_pred_path)
        
        # Feature Importance (if available)
        if feature_importance_df is not None and not feature_importance_df.empty:
            importance_path = os.path.join(plot_dir, 'feature_importance.png')
            self.plot_feature_importance(feature_importance_df, save_path=importance_path)
        
        self.logger.info("Evaluation report generated successfully!")
        self.logger.info(f"Plots saved to: {plot_dir}")
        
        return evaluation_results
