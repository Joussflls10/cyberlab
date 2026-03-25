import { Link } from 'react-router-dom'
import ProgressBar from './ProgressBar'

interface Course {
  id: string
  title: string
  description: string
  topics: number
  challenges: number
  progress: number
}

interface CourseCardProps {
  course: Course
}

export default function CourseCard({ course }: CourseCardProps) {
  return (
    <Link to={`/course/${course.id}`} className="block">
      <div className="border border-border rounded-lg bg-surface p-6 hover:border-primary transition-colors group">
        <h3 className="text-xl font-bold text-primary group-hover:text-primary mb-2">
          {course.title}
        </h3>
        <p className="text-gray-400 text-sm mb-4 line-clamp-2">
          {course.description}
        </p>
        <div className="flex items-center gap-4 text-xs text-gray-500 mb-4">
          <span>{course.topics} topics</span>
          <span>•</span>
          <span>{course.challenges} challenges</span>
        </div>
        <ProgressBar value={course.progress} max={100} />
      </div>
    </Link>
  )
}
